# agent_c — S-V1-06 run 2 (satisfied)

**Customer:** Hi! I just placed order O1014 but I used my old address. Can you ship it to 88 Cedar Lane, Springfield, IL instead? Email priya.nair@example.com.

**Agent:** Hi Priya! I’ve found your order. I can update the shipping address for you. Is this the correct new address?

88 Cedar Lane
Springfield, IL
> turn: 2017 ms | 6806p + 69c tokens | 3 API call(s) | tools: get_customer, get_order | retrieved: V1.address, V2.exchange, V1.status

**Customer:** Yes, that's correct.

**Agent:** I’ve updated the shipping address for order O1014 to 88 Cedar Lane, Springfield, IL. Your order will be shipped to this new address.
> turn: 2467 ms | 4294p + 66c tokens | 2 API call(s) | tools: update_address | retrieved: V1.lost, V2.elicit, V1.address
