# DAWA address search

## Overview

DAWA provides Danish address autocomplete, lookup, and reverse-address functionality.

It is a good conceptual fit for typed address search and GPS-based address resolution. Availability and lifecycle messaging around DAWA has changed over time, so operational status should be verified before relying on it as a long-term provider.

## Relevant endpoints

- `/autocomplete`
- `/adresser`
- `/adresser/{id}`
- `/adgangsadresser`
- `/adgangsadresser/{id}`
- `/adgangsadresser/reverse`
- `/datavask/adresser`

## How we would use it in the web app

- typed address search via `/autocomplete`
- pasted-address cleanup via `/datavask/adresser`
- GPS-to-nearest-address via `/adgangsadresser/reverse`

## Risks / open questions

- Service stability and long-term availability should be revalidated periodically
- Replacement strategy is not yet locked in
- Reverse lookup is address-entry focused and may need a second step for full address resolution

## Recommendation for this project

DAWA is acceptable as the current provider, but the app should remain provider-swappable.

Keep the lookup integration thin so an alternative provider can be introduced without changing page logic.
