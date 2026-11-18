# Price a city twin

For a new twin, `price` gives a free rough price of the full first run. It
sends no jobs. Facade batches and terrain reach are estimates, so the price
can be lower or higher than the exact price. The rough price does not validate
all inputs. An exact price and `update` validate them.

Python, with `client`, `city`, `buildings` and `payload` already set:

```python
twin = client.twin("out/city")
price = twin.price(payloads=payload, city=city, buildings=buildings)
print(price.tokens, price.rough)
exact_price = twin.price(payloads=payload, city=city, buildings=buildings, exact=True)
```

TypeScript, with `client`, `city`, `buildings` and `payload` already set:

```ts
const twin = client.twin("out/city");
const price = await twin.price({ payloads: payload, city, buildings });
console.log(price.tokens, price.rough);
const exactPrice = await twin.price({ payloads: payload, city, buildings, exact: true });
```

For a twin with a live version, `price` gives the exact price of the edit.
A first price with edits or with different geometry or terrain per payload
also uses the exact planner.
`update` always plans exactly. Read the [SDK guide](https://infrared.city/docs/sdk/)
for the full input and version rules.
