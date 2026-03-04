# AUD/CNY 汇率监控与 Telegram 提醒

监控页面：`https://www.kylc.com/huilv?ccy=aud` 中 **中国银行 - 现汇卖出价**。  
当价格低于你设置的阈值时，使用 Telegram Bot 发送提醒。

## 1. 配置

1. 复制示例环境变量文件：

```bash
cp .env.example .env
```

2. 编辑 `.env`：

```env
TG_BOT_TOKEN=你的_bot_token
TG_CHAT_ID=你的_chat_id
ALERT_PRICES=4.55,4.50,4.45
CHECK_INTERVAL_SECONDS=60
```

- `ALERT_PRICES` 支持多个价格，英文逗号分隔。
- 逻辑为“当前价 < 阈值”触发提醒。
- 同一阈值触发后不会重复提醒，直到价格重新回到该阈值上方后才会再次触发。

## 2. 本地运行

```bash
pip install -r requirements.txt
python main.py
```

## 3. Docker 运行

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

停止：

```bash
docker compose down
```
