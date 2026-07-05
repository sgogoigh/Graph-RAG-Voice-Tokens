# agent_c — S-V5-01 run 1 (satisfied)

**Customer:** Hi, I need to change the email on my account - I'm moving off this address soon. It's sarah.kim@example.com, and my order O1003 can verify me.

**Agent:** Hi Sarah, thanks for reaching out. I see your order O1003 delivered on June 30th. You can change your email address yourself in your account settings. Would you like me to walk you through that process?
> turn: 1725 ms | 4456p + 80c tokens | 2 API call(s) | tools: get_customer, get_order | retrieved: V5.update, identity-verification, V1.address

**Customer:** Yes, please. I'm logged in now.

**Agent:** Here's how to change your email address:

1. Log in to your account.
2. Click on your name or profile icon in the top-right corner.
3. Select "Settings" from the dropdown menu.
4. Click on "Account Settings".
5. Update your email address in the "Contact Information" section.
6. Save your changes.

You should receive a confirmation email at your new address.
> turn: 1635 ms | 2075p + 83c tokens | 1 API call(s) | tools: none | retrieved: V5.update, identity-verification, V5.password
