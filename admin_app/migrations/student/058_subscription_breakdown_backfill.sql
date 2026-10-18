UPDATE pcp_subscriptions
   SET list_paise = amount_paise, discount_pct = 0
 WHERE list_paise IS NULL AND status = 'active';
