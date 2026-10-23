# Square loyalty points import

`get_square_customers.py` reads Square customers created in a date range,
looks up each one's loyalty point balance, creates the customer in
BigCommerce, and writes an email/points CSV.

## Setup

`.env` in the project root:

```
SQUARE_APP_TOKEN=
STORE_HASH=
ACCESS_TOKEN=
```

```bash
pip install -r requirements.txt
```

## Commands

```bash
python get_square_customers.py --start 01/09/2026 --end 01/10/2026
```

```bash
python get_square_customers.py --start 01/09/2026
```

End date defaults to today.

```bash
python get_square_customers.py
```

Asks for the start date, end date defaults to today.

Dates are `DD/MM/YYYY`. Start is included, end is not.

## What it changes

| | |
|---|---|
| BigCommerce | **creates customers** in batches of 10, with name, phone, note and address |
| `data/production/loyalty/loyalty2.csv` | rewritten each run: email, points |
| `data/production/loyalty/square_customers.json` | every Square customer seen, with its point balance |
| `data/counter.txt` | next placeholder email number |
| `data/cursor.txt` | Square paging cursor, for resuming |
| `data/loyalty_range.txt` | the date range of the current run |

Square is only read. Nothing in Square is modified.

## Customers with no email

Square allows a customer with no email; BigCommerce requires one. Those
get a placeholder address, `requestemailaddress<n>@domain.com`, numbered
from `data/counter.txt`. `csv_of_nocontact_customers.py` lists them
afterwards.

## Resuming

The run stores its Square cursor in `data/cursor.txt`, so stopping it and
running the same command again continues from where it stopped. Changing
the date range clears that cursor automatically, so a new range always
starts from the beginning.

## Importing the points into BigCommerce

The script does not write point balances to BigCommerce; it produces the
CSV for whichever loyalty app the store uses. Upload
`data/production/loyalty/loyalty2.csv` in that app's import screen, keyed
on email.

## Files

```
get_square_customers.py        this import
csv_of_nocontact_customers.py  lists the placeholder-email customers
create_missing_customers.py    retries customers that failed to create
delete_customers.py            removes customers created by a run
```
