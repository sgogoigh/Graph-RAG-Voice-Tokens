# agent_c smoke — smoke_v1_status (S-V1-01)

**Customer:** Hi! Where is my order O1001? My email is maya.fernandes@example.com.

**Agent:** Hi Maya! Your order O1001 is on the way. It shipped on July 1st via SwiftShip (tracking number SS-88231) and should arrive by July 7th.
> turn: 3710 ms | 4182p + 62c tokens | 2 API call(s) | tools: get_order | retrieved: V1.status, V2.elicit, V1.elicit

**Customer:** Great, thanks. Will it definitely arrive by the 7th?

**Agent:** I'm sorry for any inconvenience, but I currently don't have the tools to confirm that specific delivery date for you. For the most accurate information, I recommend contacting the shipping provider directly or checking the tracking information on their website.
> turn: 1610 ms | 2152p + 48c tokens | 1 API call(s) | tools: none | retrieved: V1.status, V1.delayed, V1.lost
