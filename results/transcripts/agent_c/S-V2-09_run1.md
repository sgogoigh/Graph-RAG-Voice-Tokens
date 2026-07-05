# agent_c — S-V2-09 run 1 (satisfied)

**Customer:** Where is my refund for order O1017? It says refunded but I don't see the money. omar.haddad@example.com.

**Agent:** Hi Omar! Your refund for order O1017 was issued on June 20, 2026, and banks typically take 5–10 business days to post it to your account. That puts the expected arrival date between June 27 and July 2, 2026. If you haven't seen it by now, please check the statement for that account and let me know what you find.
> turn: 1799 ms | 4579p + 123c tokens | 2 API call(s) | tools: get_order, get_returns | retrieved: V2.refund, V2.status, Guard.fraud

**Customer:** I checked. It's not there.

**Agent:** Hi Omar, thanks for confirming. I've opened a ticket with our billing team to investigate. They'll reply within **24 hours** — usually sooner. Outside of 9am–6pm ET Mon–Fri, it's a callback ticket and they'll call you back on the first business day.
> turn: 4271 ms | 8307p + 192c tokens | 3 API call(s) | tools: get_customer, get_order, create_ticket | retrieved: V2.refund, V1.lost, V2.window
