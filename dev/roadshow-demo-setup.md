# 东升杯路演 — 飞书审批门 Demo 配置指南

本指南详述了 2026-04-24 路演中「飞书确认门」环节所需的完整配置。
核心看点：当 Agent 尝试调用 `oa__purchase_pay` 工具时，飞书群内会
弹出一张富文本卡片；演示者点击 **同意**，工具继续执行；点击 **拒绝**，
工具被拦截。

以下内容均假设 FIM One 运行在 `https://one.fim.ai`（或你为飞书配置
的任何 `BACKEND_URL`）。

---

## 1. 预置的 Demo Channel 凭据

以下是团队已经预先配置好的值。后续进入「创建 Channel」步骤时直接照抄即可。

| 字段 | 值 |
|---|---|
| App ID | `cli_a9271aab36f89bb4` |
| App Secret | `P6TzXl0kd52yQt7s4JSqMbNkGqZm4hif` |
| Chat ID | `oc_4f313b3d41ae30fbcb5a23710096982e` |
| Chat Name | `FIM One` |
| Tenant Key | `10b87b7f1897575f` |
| Owner Open ID | `ou_fd960776ebfe136028a3fea1c9257ef9` |

> 本次 Demo 将卡片发送到 **群聊**（上面的 Chat ID）。
> 该群内任何成员都可以点击 同意 / 拒绝。按 open_id 路由到
> 单人私聊的能力延迟到 v0.9，本次不使用。

---

## 2. 飞书开放平台配置

同一个 App 只需做一次——上面的值均已配置完毕。

1. 访问 <https://open.feishu.cn/app/> → 登录 → 打开应用
   `cli_a9271aab36f89bb4`。
2. 在 **凭证与基础信息** 中确认 App Secret 一致。
3. 在 **权限与范围** 中确保以下权限已开通：
   - `im:message`（发送消息）
   - `im:message:send_as_bot`
   - `im:chat`（读写群聊）
   - `im:chat:readonly`（至少）
4. 在 **事件订阅** → **请求地址** 中填入：
   ```
   https://one.fim.ai/api/channels/<CHANNEL_ID>/callback
   ```
   （`<CHANNEL_ID>` 从下文第 4 节获取）。点击 **验证**——飞书会向
   该地址 POST `{"type":"url_verification","challenge":"..."}`，
   我们的回调会把 `challenge` 原样返回。
5. 在 **机器人** → **功能** 中启用 **消息卡片交互**。
   这样用户点击我们的 同意/拒绝 按钮后，事件才会被投递到同一个
   请求地址。
6. （可选但推荐）在 **事件订阅** → **加密策略** 中设置
   **Verification Token** 和 **Encrypt Key**。在下一步创建 Channel
   时把这两个值填入 `config`——我们的 `verify_signature()` 会用
   Encrypt Key 校验每一个回调请求。
7. 把机器人拉进 `FIM One` 群（`oc_4f313b...`）。

---

## 3. Mock 数据源

### 3.1 MySQL — 历史采购数据

把以下 SQL 跑到任意本地 MySQL（Demo 使用 `demo_oa`）：

```sql
CREATE DATABASE IF NOT EXISTS demo_oa CHARACTER SET utf8mb4;
USE demo_oa;

CREATE TABLE IF NOT EXISTS purchase_history (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    vendor       VARCHAR(100) NOT NULL,
    item         VARCHAR(200) NOT NULL,
    amount_cny   DECIMAL(12,2) NOT NULL,
    ordered_at   DATETIME NOT NULL,
    status       VARCHAR(20) NOT NULL
);

INSERT INTO purchase_history (vendor, item, amount_cny, ordered_at, status) VALUES
 ('北京智成科技', '高性能服务器 DL380', 128000.00, '2026-02-14 10:22:00', 'paid'),
 ('北京智成科技', 'SSD 存储 3.84TB x 8', 65200.00, '2026-03-02 14:05:00', 'paid'),
 ('上海卓越耗材', '办公耗材季度套餐',  18200.00, '2026-03-18 09:41:00', 'paid'),
 ('深圳领航数据', '内部审计数据服务',  58000.00, '2026-03-25 16:12:00', 'paid'),
 ('北京智成科技', 'GPU A100 x 2',     240000.00, '2026-04-05 11:08:00', 'pending_approval');
```

在 FIM One 中注册：

1. 门户 → **连接器** → **新建数据库连接器**。
2. 填入本地 MySQL 的 Host / 端口 / 数据库 / 用户名 / 密码。
3. 命名为 `oa_mysql`。点击 **探测 Schema** → 确认列表中包含
   `purchase_history`。
4. 保存。

### 3.2 飞书文档 — 合同草稿

要么在 <https://hzn5uy7d2w.feishu.cn/docx/DemoContractDraft>
创建一篇真正的飞书文档并粘贴一份一页的合同模板，**或者** 通过把
一个 markdown 文件放到 `uploads/kb/demo-contracts/contract-2026-04.md`
并将该知识库挂到 Demo Agent 上来 Mock。Agent 只需要 _读取_ 文档
标题和条目，两种方式都可以。

### 3.3 OA HTTP Webhook — 「支付」工具

在本地跑一个极简的 webhook 接收端：

```python
# scripts/demo_oa_webhook.py
from fastapi import FastAPI, Request
app = FastAPI()

@app.post("/oa/purchase/pay")
async def pay(req: Request):
    body = await req.json()
    print("Mock OA received pay request:", body)
    return {"ok": True, "po_id": "PO-2026-0418"}
```

用 `uvicorn scripts.demo_oa_webhook:app --port 7799` 启动它。

然后在 FIM One 中：

1. 门户 → **连接器** → **新建 HTTP 连接器**。
2. Base URL：`http://localhost:7799`。
3. 添加一个 action：
   - 名称：`purchase_pay`
   - Method：`POST`
   - Path：`/oa/purchase/pay`
   - `requires_confirmation`：**打开**——这正是触发
     `FeishuGateHook` 的开关。
   - 参数 Schema：
     ```json
     {
       "type":"object",
       "properties":{
         "vendor":{"type":"string"},
         "item":{"type":"string"},
         "amount_cny":{"type":"number"}
       },
       "required":["vendor","item","amount_cny"]
     }
     ```

---

## 4. 在 FIM One 中创建飞书 Channel

1. 以即将演示的组织的 **Org Owner**（或 Admin）身份登录门户。
2. 门户 → **组织设置** → **Channels** → **新建 Channel**。
   （如果 UI 还没接通，可以直接 `POST /api/channels`：
   ```json
   {
     "name": "FIM One Demo Feishu",
     "type": "feishu",
     "org_id": "<YOUR_ORG_ID>",
     "is_active": true,
     "config": {
       "app_id": "cli_a9271aab36f89bb4",
       "app_secret": "P6TzXl0kd52yQt7s4JSqMbNkGqZm4hif",
       "chat_id": "oc_4f313b3d41ae30fbcb5a23710096982e",
       "verification_token": "<从飞书控制台复制>",
       "encrypt_key": "<从飞书控制台复制>"
     }
   }
   ```
   响应会返回 `id`（即 `<CHANNEL_ID>`）和 `callback_url`。）
3. 从响应中复制 `callback_url` — 粘贴到飞书应用的
   **事件订阅 → 请求地址**。点击 **验证**。
4. 回到门户，点击 **发送测试消息**。查看 FIM One 群——应该能看到
   一条纯文本 `FIM One test message from <your email>`。
   如果能看到，说明 Channel 已经联通。

---

## 5. Demo Agent 配置

门户 → **Agents** → **新建 Agent**，填入：

- **名称**：`采购审批助手 Procurement Assistant`
- **头像**：任选
- **System Prompt**（复制粘贴）：
  ```
  你是 FIM One 的采购审批助手。当用户询问历史采购记录时，从
  oa_mysql 的 purchase_history 表查询。当用户要求执行一笔支付时，
  先用 oa_mysql 验证该供应商过去一年内的累计采购金额，再调用
  oa_http.purchase_pay 提交付款。所有付款动作都需要人工审批。
  回答必须简洁，用中文。
  ```
- **工具 / 连接器**：加上 `oa_mysql` 和 `oa_http`（其中包含
  `purchase_pay`）。
- **Hooks**：启用 `feishu_gate`。（如果 Agent UI 还没暴露该配置，
  可通过 `PATCH /api/agents/{id}` 或 Agent JSON 编辑器设置
  `model_config_json.hooks = {"class_hooks": ["feishu_gate"]}`。）
- 保存。

---

## 6. 一键冒烟测试

在以上所有配置完成后，从仓库根目录执行：

```bash
# 前置条件：
#   1. ./start.sh 已经启动后端
#   2. scripts/demo_oa_webhook.py 正在 :7799 监听
#   3. 飞书 Channel 已创建且测试消息发送成功
#
# 把 <AGENT_ID> 和 <AUTH_TOKEN> 替换为你所在组织的真实值。

curl -N -X POST https://one.fim.ai/api/react \
  -H "Authorization: Bearer <AUTH_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<AGENT_ID>",
    "message": "请帮我给北京智成科技支付 GPU A100 两张的尾款 240000 元"
  }'
```

你会依次观察到：

1. Agent 对 `purchase_history` 发起 MySQL 查询，并总结该供应商
   近期的消费情况。
2. 在 `purchase_pay` 真正触发之前，`FIM One` 群内弹出一张
   飞书交互卡片，带 **同意** / **拒绝** 按钮。
3. SSE 流显示 Agent 正在等待。
4. 点击 **同意** — SSE 流恢复；Mock webhook 打印出收到的 payload；
   Agent 宣布执行成功。
5. 重跑同一条 curl，这次点击 **拒绝** — Agent 会报告工具被
   操作员拦截。

---

## 7. 当天演示者 Cheat Sheet（5 步）

舞台上展示 / 打印出来备用：

1. 在演示笔记本上执行 `./start.sh` → 后端运行在
   `https://one.fim.ai`。
2. 在第二个终端执行 `uvicorn scripts.demo_oa_webhook:app --port 7799`
   → Mock OA 起来。
3. 登录门户，打开 `采购审批助手` Agent，点击 **Chat**。
4. 输入排练过的 Prompt（见上文第 6 节）。在第二块屏幕上盯着
   飞书群，等卡片弹出。
5. 在飞书卡片上点击 **同意** → Agent 完成。搞定。

如果 3 秒内卡片没有出现：
- 确认 Channel 记录的 `is_active = true`
- 确认飞书控制台的请求地址与 `GET /api/channels/{id}` 返回的
  `callback_url` 一致
- 检查 `docker logs fim-one-api | grep feishu_gate`
