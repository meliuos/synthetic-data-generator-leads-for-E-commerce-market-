SELECT 'events_total' AS check_name, toString(count()) AS value
FROM retailrocket_raw.events;

SELECT 'item_properties_total' AS check_name, toString(count()) AS value
FROM retailrocket_raw.item_properties;

SELECT 'category_tree_total' AS check_name, toString(count()) AS value
FROM retailrocket_raw.category_tree;

SELECT event_type, count() AS rows
FROM retailrocket_raw.events
GROUP BY event_type
ORDER BY event_type;

SELECT
    round(100.0 * countIf(il.category_id IS NOT NULL) / count(), 2) AS pct_with_category
FROM retailrocket_raw.events e
LEFT JOIN retailrocket_raw.item_latest il ON il.item_id = e.item_id;
