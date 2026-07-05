# agent_a — ST-02 run 1 (satisfied)

**Customer:** Hi! I have a little list to get through today if that's okay. First: where is my order O1001? maya.fernandes@example.com.

**Agent:** Hi Maya! Your order O1001 is on the way. It shipped on July 1st via SwiftShip, tracking number SS-88231, and should arrive by July 7th.
> turn: 1470 ms | 11508p + 62c tokens | 2 API call(s) | tools: get_order

**Customer:** Thanks! Next: I was charged twice for order O1011.

**Agent:** I see your order O1011, Maya. It's currently processing and not yet shipped. The total is $95.00.

Double charges often happen because of temporary authorization holds from your bank. These holds usually drop off automatically in 3–5 business days. Could you check if both charges are marked as "posted" or "settled"? If one is a hold, it should disappear on its own soon. If both are posted, let me know the amounts and dates, and I'll open a billing investigation for you.
> turn: 1751 ms | 11597p + 154c tokens | 2 API call(s) | tools: get_order
