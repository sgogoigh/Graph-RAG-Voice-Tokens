# agent_b smoke — smoke_v1_status (S-V1-01)

**Customer:** Hi! Where is my order O1001? My email is maya.fernandes@example.com.

**Agent:** Your order O1001 has shipped via SwiftShip with tracking number SS-88231. It's expected to be delivered by July 7, 2026. You can track the status of your shipment using the tracking number provided.
> turn: 2392 ms | 5510p + 265c tokens | 3 API call(s) | tools: get_customer, get_order | node: ord_status

**Customer:** Great, thanks. Will it definitely arrive by the 7th?

**Agent:** The expected delivery date of July 7, 2026, is an estimate and not guaranteed. However, based on the tracking information, it's likely to arrive by then. If there are any issues, you can track the shipment using the tracking number SS-88231.
> turn: 1470 ms | 5392p + 326c tokens | 3 API call(s) | tools: get_customer | node: ord_status
