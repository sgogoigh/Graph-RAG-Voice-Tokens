# agent_b_spec smoke — smoke_v1_status (S-V1-01)

**Customer:** Hi! Where is my order O1001? My email is maya.fernandes@example.com.

**Agent:** Hi Maya! Your order O1001 is on the way. It shipped on July 1st and is expected to arrive by July 7th. The carrier is SwiftShip and the tracking number is SS-88231.
> turn: 2600 ms | 5067p + 71c tokens | 3 API call(s) | tools: get_order | node: ord_status

**Customer:** Great, thanks. Will it definitely arrive by the 7th?

**Agent:** I'm sorry, but I can't guarantee the delivery date. The expected delivery date is an estimate, and while we aim to meet it, delays can happen. Your order is currently on track with an expected delivery date of July 7th.
> turn: 742 ms | 2934p + 54c tokens | 2 API call(s) | tools: none | node: ord_status
