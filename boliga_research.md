# Boliga endpoint notes

Date checked: 2026-05-14

## Page inspected

`https://www.boliga.dk/boliger/fritidshuse`

The rendered page shows:

- 8,118 fritidshus results
- 50 results per page
- 163 pages
- Pagination pattern on the website: `/boliger/fritidshuse?page=2`
- Listing URL pattern: `/adresse/{slug}-{id}` and sometimes `/adresse/{slug}-{id}?e={estate_id}`

## JSON API endpoint

The active-listing endpoint used by Boliga is:

`https://api.boliga.dk/api/v2/search/results`

Useful query parameters:

- `searchTab=1`
- `propertyType=4` for fritidshus / holiday homes
- `page=1`, `page=2`, ...
- `pagesize=50`
- `sort=daysForSale-a` for newest/shortest days-on-market first

Example:

`https://api.boliga.dk/api/v2/search/results?searchTab=1&propertyType=4&page=1&pagesize=50&sort=daysForSale-a`

## Headers

The scraper sends ordinary browser-like JSON headers:

- `Accept: application/json, text/plain, */*`
- `Accept-Language: da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7`
- `Origin: https://www.boliga.dk`
- `Referer: https://www.boliga.dk/boliger/fritidshuse`
- `User-Agent: Mozilla/5.0 ... Chrome ... Safari/537.36`

## Important blocking note

Direct local `requests`/PowerShell calls from this machine currently receive a Cloudflare "Enable JavaScript and cookies to continue" challenge from `api.boliga.dk` instead of JSON. The scraper detects this and gives a clear error. If Boliga allows the request later, or if you provide valid browser cookies via `BOLIGA_COOKIE`, the same code will parse and store the JSON.

This matters because the project should not pretend it scraped real API JSON when the server returned a challenge page.
