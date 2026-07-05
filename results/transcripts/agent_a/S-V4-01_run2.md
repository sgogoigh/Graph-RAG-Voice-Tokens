# agent_a — S-V4-01 run 2 (satisfied)

**Customer:** I just checked my card and I was charged TWICE for order O1011. Fix this please. maya.fernandes@example.com.

**Agent:** Hi Maya, thanks for reaching out. I pulled up your order O1011 and see it’s currently processing. It’s possible your bank temporarily held the amount and then charged it again. This usually sorts itself out in 3–5 business days. Could you check if both charges say "Posted" or "Completed"? If one says "Pending", that’s likely the temporary hold and should drop off soon. If they’re both posted, let me know the amounts and dates, and I’ll open a billing ticket for you.
> turn: 1554 ms | 11351p + 126c tokens | 2 API call(s) | tools: get_order

**Customer:** Both charges say POSTED. $59.99 on 10/10 and $59.99 on 10/12.

**Agent:** Thanks for confirming, Maya. I’ve opened a billing ticket for you with our team. They’ll look into the duplicate charges and get back to you within one business day. Since it’s currently 6:30pm ET on a Friday, you’ll hear from them on Monday at the latest.
> turn: 2646 ms | 17733p + 151c tokens | 3 API call(s) | tools: get_order, create_ticket
