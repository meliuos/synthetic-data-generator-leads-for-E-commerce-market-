const test = require('node:test');
const assert = require('node:assert/strict');

const tracker = require('./index');

test('productView queues a product_view event', () => {
  tracker.reset();
  const event = tracker.productView({
    product_id: 'SKU-1',
    category: 'electronics',
    price: 19.99,
    currency: 'USD'
  });

  assert.equal(event.type, 'product_view');
  assert.equal(event.product_id, 'SKU-1');
  assert.equal(tracker.getEventQueue().length, 1);
});

test('addToCart and removeFromCart emit expected events', () => {
  tracker.reset();

  const addEvent = tracker.addToCart({
    product_id: 'SKU-2',
    quantity: 2,
    price: 10.0,
    category: 'cables'
  });
  const removeEvent = tracker.removeFromCart({
    product_id: 'SKU-2',
    quantity: 1
  });

  assert.equal(addEvent.type, 'add_to_cart');
  assert.equal(removeEvent.type, 'remove_from_cart');
  assert.equal(tracker.getEventQueue().length, 2);
});

test('purchase emits once per order_id (dedup)', () => {
  tracker.reset();

  const first = tracker.purchase({
    order_id: 'ORDER-1',
    total: 30,
    currency: 'USD',
    items: [
      { product_id: 'SKU-3', quantity: 1, price: 10, category: 'audio' },
      { product_id: 'SKU-4', quantity: 2, price: 10, category: 'audio' }
    ]
  });

  const duplicate = tracker.purchase({
    order_id: 'ORDER-1',
    total: 30,
    currency: 'USD',
    items: [{ product_id: 'SKU-3', quantity: 3, price: 10 }]
  });

  assert.equal(first.type, 'purchase');
  assert.equal(duplicate, null);
  assert.equal(tracker.getEventQueue().length, 1);
});

test('search emits expected query payload', () => {
  tracker.reset();

  const event = tracker.search({
    query: 'wireless headphones',
    results_count: 12
  });

  assert.equal(event.type, 'search');
  assert.equal(event.query, 'wireless headphones');
  assert.equal(event.results_count, 12);
});

test('ecommerce methods respect consent gate when denied', () => {
  tracker.reset();
  tracker.initTracker({ hasConsent: () => false });

  const a = tracker.productView({ product_id: 'SKU-8', category: 'x', price: 1, currency: 'USD' });
  const b = tracker.addToCart({ product_id: 'SKU-8', quantity: 1, price: 1 });
  const c = tracker.removeFromCart({ product_id: 'SKU-8', quantity: 1 });
  const d = tracker.purchase({ order_id: 'ORDER-CONSENT', total: 1, items: [] });
  const e = tracker.search({ query: 'x', results_count: 1 });

  assert.equal(a, null);
  assert.equal(b, null);
  assert.equal(c, null);
  assert.equal(d, null);
  assert.equal(e, null);
  assert.equal(tracker.getEventQueue().length, 0);

  tracker.initTracker({ hasConsent: () => true });
});
