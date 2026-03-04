import os
import re
import time
import random
import logging
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

URL = "https://www.kylc.com/huilv?ccy=aud"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def parse_alert_prices(raw: str) -> List[float]:
    if not raw:
        raise ValueError("ALERT_PRICES 未配置")

    prices: List[float] = []
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        prices.append(float(text))

    if not prices:
        raise ValueError("ALERT_PRICES 未解析出有效价格")

    return sorted(set(prices), reverse=True)


def load_config() -> Dict[str, object]:
    load_dotenv()

    tg_bot_token = os.getenv("TG_BOT_TOKEN", "").strip()
    tg_chat_id = os.getenv("TG_CHAT_ID", "").strip()
    alert_prices_raw = os.getenv("ALERT_PRICES", "").strip()
    min_interval_raw = os.getenv("CHECK_INTERVAL_MIN_SECONDS", "").strip()
    max_interval_raw = os.getenv("CHECK_INTERVAL_MAX_SECONDS", "").strip()
    fixed_interval_raw = os.getenv("CHECK_INTERVAL_SECONDS", "").strip()

    if not tg_bot_token:
        raise ValueError("TG_BOT_TOKEN 未配置")
    if not tg_chat_id:
        raise ValueError("TG_CHAT_ID 未配置")

    alert_prices = parse_alert_prices(alert_prices_raw)

    if min_interval_raw and max_interval_raw:
        min_interval = int(min_interval_raw)
        max_interval = int(max_interval_raw)
    else:
        fixed_interval = int(fixed_interval_raw or "60")
        min_interval = fixed_interval
        max_interval = fixed_interval

    if min_interval <= 0 or max_interval <= 0:
        raise ValueError("轮询间隔必须大于 0")
    if min_interval > max_interval:
        raise ValueError("CHECK_INTERVAL_MIN_SECONDS 不能大于 CHECK_INTERVAL_MAX_SECONDS")

    return {
        "tg_bot_token": tg_bot_token,
        "tg_chat_id": tg_chat_id,
        "alert_prices": alert_prices,
        "check_interval_min": min_interval,
        "check_interval_max": max_interval,
    }


def fetch_boc_spot_sell_aud(timeout: int = 20) -> Optional[float]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(URL, headers=headers, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    def extract_float(text: str) -> Optional[float]:
        match = re.search(r"\d+(?:\.\d+)?", text)
        if not match:
            return None
        return float(match.group(0))

    aud_table = soup.find("table", id="bank_huilvtable_aud")
    if aud_table is not None:
        for row in aud_table.select("tbody tr"):
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            bank_name = cols[0].get_text(" ", strip=True)
            if "中国银行" not in bank_name:
                continue

            spot_sell_text = cols[4].get_text(" ", strip=True)
            value = extract_float(spot_sell_text)
            if value is None:
                raise RuntimeError(f"中国银行现汇卖出价解析失败: {spot_sell_text}")
            return value

    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 6:
            continue

        bank_name = cols[0].get_text(" ", strip=True)
        ccy_name = cols[1].get_text(" ", strip=True)
        if "中国银行" not in bank_name or "澳大利亚元" not in ccy_name:
            continue

        value = extract_float(cols[4].get_text(" ", strip=True))
        if value is not None:
            return value

    raise RuntimeError("未找到中国银行澳元现汇卖出价")


def send_telegram_message(token: str, chat_id: str, text: str, timeout: int = 20) -> None:
    api = TELEGRAM_API.format(token=token)
    resp = requests.post(
        api,
        data={"chat_id": chat_id, "text": text},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram 发送失败: {data}")


def monitor() -> None:
    cfg = load_config()

    token = str(cfg["tg_bot_token"])
    chat_id = str(cfg["tg_chat_id"])
    alert_prices = list(cfg["alert_prices"])
    check_interval_min = int(cfg["check_interval_min"])
    check_interval_max = int(cfg["check_interval_max"])

    notified: Dict[float, bool] = {price: False for price in alert_prices}

    logging.info(
        "监控已启动，提醒价: %s，间隔区间: %s~%ss",
        alert_prices,
        check_interval_min,
        check_interval_max,
    )

    while True:
        try:
            rate = fetch_boc_spot_sell_aud()
            logging.info("当前中国银行 澳元现汇卖出价: %.4f", rate)

            for threshold in alert_prices:
                if rate < threshold:
                    if not notified[threshold]:
                        msg = (
                            "【AUD/CNY 价格提醒】\n"
                            f"当前中国银行澳元现汇卖出价: {rate:.4f}\n"
                            f"已低于提醒价: {threshold:.4f}\n"
                            f"来源: {URL}"
                        )
                        send_telegram_message(token, chat_id, msg)
                        notified[threshold] = True
                        logging.info("已发送提醒，阈值: %.4f", threshold)
                else:
                    if notified[threshold]:
                        logging.info("价格回到阈值上方，重置提醒状态: %.4f", threshold)
                    notified[threshold] = False

        except Exception as exc:
            logging.exception("监控循环异常: %s", exc)

        sleep_seconds = random.uniform(check_interval_min, check_interval_max)
        logging.info("下次检查等待: %.2fs", sleep_seconds)
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    setup_logging()
    monitor()
