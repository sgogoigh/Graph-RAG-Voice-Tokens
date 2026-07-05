# agent_c — S-V4-01 run 2 (frustrated)

**Customer:** I just checked my card and I was charged TWICE for order O1011. Fix this please. maya.fernandes@example.com.

**Agent:** Hi Maya. I see your order. It’s common for cards to show a temporary hold alongside the real charge — the holds usually drop off in 3–5 business days. Do both charges say "posted" or "settled"?
> turn: 1724 ms | 4425p + 66c tokens | 2 API call(s) | tools: get_order | retrieved: V4.duplicate, Guard.fraud, V4.failed

**Customer:** BOTH SAY POSTED. I don’t want to wait 5 days.

**Agent:** I’ve created a ticket for our billing team to investigate the duplicate charge on your order. They’ll respond by **tomorrow evening** if not sooner. Can I help with anything else?
> turn: 2625 ms | 7355p + 124c tokens | 3 API call(s) | tools: get_order, create_ticket | retrieved: V1.lost, V4.duplicate, V1.delayed
