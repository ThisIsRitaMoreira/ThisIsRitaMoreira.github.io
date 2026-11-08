# Alaska + Hawaiian (2024): data schema

Two generated files feed the "real merger" part of Case 03 and the fleet map of Case 04.
Do not edit them by hand. Rebuild with:

    python -I analysis/airline_bts.py <bts_zip_dir> <ourairports airports.csv> <filtered.csv.gz> data/airline_real.js
    python -I analysis/geo_basemaps.py <countries-50m.json> <states-10m.json> data/airline_real.js <city_hotspots.csv> data/geo.js

`airline_bts.py` caches the AS/HA rows in `<filtered.csv.gz>`. Delete that file to re-read the zips.
`geo_basemaps.py` reads `data/airline_real.js` for the airport list, so run it second.

## Sources

| Data | Source | Licence |
|---|---|---|
| Flights | BTS Reporting Carrier On-Time Performance (1987-present), 2024, all 12 monthly zips | US public domain |
| Airport coordinates | OurAirports `airports.csv` (matched on `iata_code`) | Public domain |
| Land, borders, states | Natural Earth via `world-atlas@2/countries-50m.json` and `us-atlas@3/states-10m.json` | ISC (Natural Earth: public domain) |
| Fleet cities | BUAN 6346 project `analytics/output/city_hotspots.csv` | Course project |

**Scope.** BTS covers each reporting carrier's own *domestic* scheduled flights. It leaves out
Alaska's regional partners (Horizon QX and SkyWest OO, which fly as "Alaska") and every
international flight (Mexico, Canada, Costa Rica, Japan, Australia and so on). American Samoa
(PPG) counts as domestic, so it is included. Hawaiian kept reporting under HA for all of 2024.

## Conventions

* **Tables** are `{cols:[...], rows:[[...], ...]}`. Values in a row follow `cols`. `null` means
  missing or not applicable.
* **Rates and shares** are fractions from 0 to 1, rounded to 4 decimals.
* **Delays** are in minutes. `dep_delay` and `arr_delay` are signed (negative = early).
  BTS fills the cause minutes (carrier, weather, NAS, security, late aircraft) only for flights
  that arrive 15 or more minutes late. On other flights they are `null`.
* **Replay times** in `worst_day.flights`, `worst_day.hourly` and `propagation.chains` are
  integer **minutes since 00:00 UTC on the worst day** (`worst_day.utc_zero`, `2024-01-17T00:00Z`).
  Values above 1440 fall on the next UTC day. In the file, times run from 555 (09:15Z) to 2660.
* **Flight date** follows BTS `FlightDate`: the *local* scheduled departure date at the origin.
* **Local to UTC.** Each airport gets an IANA zone: the state default, plus overrides for split
  states (for example `ADK = America/Adak`, `ELP = America/Denver`, `PPG = Pacific/Pago_Pago`).
  2024 DST rules apply: Hawaii, Arizona and American Samoa have no DST. A DST gap shifts
  forward, and a repeated hour takes the DST reading. A scheduled arrival moves to the next day
  when `CRSElapsedTime` requires it. Actual time = scheduled time + BTS delay.
  **Check:** for all 324,349 flights, `sched_arr - sched_dep` equals `CRSElapsedTime`
  (0 mismatches). For all 318,934 flights with a `DepTime`, the computed local clock matches
  `DepTime` (0 mismatches).

## Metric definitions

| Name | Definition |
|---|---|
| scheduled flights (`flights`) | All rows reported to BTS, including cancelled ones |
| `completed` | Not cancelled (includes diverted) |
| `arrived` | Completed, not diverted, with an `ArrDelay` |
| **A0** | Share of `arrived` with `ArrDelay <= 0` |
| **A14** | Share of `arrived` with `ArrDel15 == 0`, i.e. arrival delay of 14 minutes or less. This is the course standard and the same as the DOT "on-time" cut |
| **A30** | Share of `arrived` with `ArrDelay <= 30` |
| `a14_of_scheduled` | A14 arrivals / *scheduled* flights, so cancellations and diversions count as not on time |
| D0 / D14 | Departure equivalents over completed flights (`DepDelay <= 0` and `DepDel15 == 0`) |
| `cause_share` | Each cause's minutes / sum of the five cause columns |
| late-aircraft share | `LateAircraftDelay` minutes / all cause minutes. This is how much delay is inherited from the aircraft's previous leg |
| disrupted | Cancelled, diverted, or arrived 15+ minutes late (`ArrDel15 == 1`) |
| disruption share | disrupted / scheduled, pooled over AS+HA (so each carrier weighs by its volume) |
| worst day | Highest disruption share in 2024. Ties are broken by disrupted count |
| market | Undirected airport pair (`a < b` alphabetically). Flights in both directions are summed |
| cascade | A leg that arrives 15+ minutes late (or is diverted), followed by successive legs of the same tail that each have `LateAircraftDelay > 0` |

---

## `data/airline_real.js` -> `window.DATA_AIRLINE_REAL`

### `meta`
`source`, `carriers` {AS, HA: names}, `year`, `months_loaded` [1..12], `flights` (324349),
`merger_close` ("2024-09-18"), `scope_note`,
`time_check` {flights_checked, elapsed_mismatch, mismatch_by_airport_pair, dep_clock_checked, dep_clock_mismatch},
`missing_coords` [airport codes without coordinates; empty].

### `carriers.AS`, `carriers.HA` (full year) and `combined` (AS+HA)
`flights`, `completed`, `cancelled`, `diverted`, `arrived`, `cancel_rate`, `divert_rate`,
`otp` {A0, A14, A30}, `a14_of_scheduled`, `dep` {D0, D14}, `avg_arr_delay` and `median_arr_delay` (minutes, arrived flights),
`cause_minutes` {carrier, weather, nas, security, late_aircraft} (minutes),
`cause_share` {same keys}.
`carriers.*` also have `name`, `tails` (distinct tail numbers), `airports`, `markets`.

### `network`
* `airports`: table `code, city, state, lat, lon, AS, HA, tz`. `AS` and `HA` are the scheduled
  **departures** from that airport in 2024. `tz` is the IANA zone used. There are 93 airports.
* `markets`: table `a, b, AS, HA, miles`. Flights each way are summed, and `miles` is the BTS
  distance. There are 228 markets, sorted with the overlap markets first.
* `overlap`: `markets` {AS, HA}, `markets_both`, `markets_total`, `flights_in_overlap` {AS, HA},
  `share_in_overlap` {AS, HA} (share of that carrier's flights), `airports` {AS, HA},
  `airports_both` [codes], `airports_total`, `overlap_markets` [[market, AS flights, HA flights]].
* `hubs`: {AS, HA}, each a list of `[airport, departures, share of the carrier's departures]`, top 10.
* `geography`: {AS, HA}, each with `touch_hawaii` and `touch_alaska` (share of flights with an
  end in HI or AK) and `segments` {inter-island | Hawaii-mainland | intra-Alaska | Alaska-Lower 48 | Lower 48: flights}.

### `monthly`
Table `month, carrier, flights, cancelled, cancel_rate, diverted, arrived, A0, A14, A30, avg_arr_delay, late_aircraft_share`
(24 rows), plus `merger_close_month` (9) and `merger_close`.

### `daily`
Table `date, flights, disrupted, share, cancelled, AS_share, HA_share` (366 rows, AS+HA, by local flight date).

### `worst_day`
* `date` ("2024-01-17"), `definition` (text), `utc_zero` ("2024-01-17T00:00Z"), `year_median_share`.
* `ranking`: the top 6 days by disruption share. Each is a *day row*:
  `{date, flights, disrupted, share, cancelled, diverted, late15, AS_share, HA_share}`.
* `worst_by_count`: a day row for the highest disrupted *count* (2024-01-11).
* `worst_by_month`: 12 day rows, the worst day in each month.
* `by_carrier` {AS, HA}: the same KPI block as `carriers.*`, for that day only.
* `cancel_codes` {Carrier | Weather | National Air System | Security: count} and `cancel_codes_by_carrier` {AS, HA: {...}}.
* `flights`: table with **every AS/HA flight** of the day (717 rows), sorted by `sched_dep`:

  | col | meaning |
  |---|---|
  | `carrier`, `flight`, `tail` | operating carrier, flight number (int), tail number |
  | `origin`, `dest` | IATA codes |
  | `sched_dep`, `act_dep` | gate departure, in replay minutes (UTC). `act_dep` is null if cancelled |
  | `sched_arr`, `act_arr` | gate arrival, in replay minutes. `act_arr` is null if cancelled, or if diverted and never reached the destination. For a diverted flight that did reach it, the time is BTS `DivArrDelay` |
  | `wheels_off`, `wheels_on` | `act_dep + TaxiOut` and `act_arr - TaxiIn` (null for diverted flights) |
  | `dep_delay`, `arr_delay` | minutes, signed |
  | `cancelled`, `diverted` | 0 or 1 |
  | `cancel_code` | A carrier, B weather, C NAS, D security (null if not cancelled) |
  | `carrier_delay`, `weather_delay`, `nas_delay`, `security_delay`, `late_aircraft_delay` | cause minutes |
  | `div_airport` | first diversion airport (null if not diverted) |

  BTS sometimes reports a gate departure before a cancellation. In the replay a cancelled flight
  never departs, so its actual times are dropped.
* `hourly`: table `hour_utc, sched_dep, cancelled, departed, dep_delayed15, arrived, arr_late15, airborne`.
  `hour_utc = h` covers replay minutes `[60h, 60h+60)`, so `h >= 24` is the next UTC day
  (36 rows, h = 9..44). Each column counts as follows:
  * `sched_dep` and `cancelled` by scheduled departure hour.
  * `departed` and `dep_delayed15` (15+ minutes late) by actual departure hour.
  * `arrived` and `arr_late15` by actual arrival hour.
  * `airborne`: flights in the air at any time during the hour (wheels-off to wheels-on). Diverted
    flights that never reached their destination are excluded.
* `top_airports`: the 5 origins with the most disrupted departures, each
  `{airport, departures, cancelled, dep_delayed15, disrupted, share, avg_dep_delay, dep_delay_min}`.
  The delay figures use operated (not cancelled) departures only.

### `propagation`
* `late_aircraft_share_year` {AS, HA} and `late_aircraft_share_worst_day` {AS, HA}.
* `tails_with_cascade_3plus` {AS, HA}: tails with a cascade of 3 or more legs on the worst day.
* `definition`: text.
* `chains`: 3 tails, picked as the longest cascade per carrier, then the next longest overall. Each is:
  `{tail, carrier, cascade_legs, late_aircraft_min, legs: table}`, where `legs` has the columns
  `flight, origin, dest, sched_dep, act_dep, sched_arr, act_arr, dep_delay, arr_delay, late_aircraft_delay, carrier_delay, weather_delay, nas_delay, cancelled, diverted, sched_turn, actual_turn`.
  The table is the tail's whole rotation that day. Times are replay minutes.
  `sched_turn` and `actual_turn` are the minutes between the previous leg's arrival and this
  leg's departure (scheduled and actual).

### `canonical`
* `key_format`: `operating_carrier|flight_number|sched_dep_date_utc|origin`. `a14_rule` is text.
* `examples`: 6 real flights from the worst day (3 AS, 3 HA). Each is `{source, canonical}`.
  * `source` holds the BTS field names and raw values: `Reporting_Airline, Flight_Number_Reporting_Airline,
    FlightDate, Tail_Number, Origin, Dest, CRSDepTime, DepTime, CRSArrTime, ArrTime, CRSElapsedTime,
    DepDelay, ArrDelay, ArrDel15, Cancelled, CancellationCode, Diverted`. The clock times are
    local "hhmm" text.
  * `canonical` holds `leg_key, operating_carrier, flight_number, sched_dep_date_utc, origin, dest, tail,
    origin_tz, dest_tz, origin_utc_offset_h, dest_utc_offset_h, sched_dep_utc, act_dep_utc, sched_arr_utc,
    act_arr_utc` (ISO `YYYY-MM-DDTHH:MMZ`), plus `arr_delay_min`, `status` (arrived | cancelled | diverted),
    `a14` (true | false | null) and `local_date_differs`.
  * The set covers 2 flights whose UTC date differs from their local date, 2 that arrived late,
    1 cancelled flight and 1 inter-island flight.
* `key_collisions`: tests the key on all 324,349 flights.
  * `utc_date_key` {groups, flights, and a table `carrier, flight, local_date, local_dep, origin, dest, sched_dep_date_utc, sched_dep_utc`}
  * `local_date_key` {groups}
  * `flights_tested`
* `share_local_date_ne_utc_date` {AS, HA}: share of flights whose UTC departure date is not their local date.

---

## `data/geo.js` -> `window.DATA_GEO`

Both maps use one projection: a spherical **Lambert azimuthal equal-area**, centred on each map.
Hawaii, Alaska and American Samoa are in their true positions, with no insets. To place more
points, use `proj` (angles in radians):

    k = sqrt(2 / (1 + sin(lat0)*sin(lat) + cos(lat0)*cos(lat)*cos(lon - lon0)))
    x = k*cos(lat)*sin(lon - lon0);   y = k*(cos(lat0)*sin(lat) - sin(lat0)*cos(lat)*cos(lon - lon0))
    X = (x - x0) * s;                 Y = (y0 - y) * s

Paths are SVG `d` strings on a 0.1 px grid. Each subpath starts with an absolute `M x y`,
continues with relative `l dx dy ...`, and closed rings end with `z`, so concatenated subpaths
stay valid. Arcs were simplified with Douglas-Peucker: 0.45 px for `pacific`, 0.35 px for `west`.

### `pacific`
* `viewBox`: "0 0 1000 917". This is the full frame and includes Pago Pago (PPG, 14 S).
* `viewBoxMain`: "0 0 1000 603". A crop of the same frame without the empty South Pacific;
  everything except PPG is inside it. `outside_main` lists the codes left out (["PPG"]).
* `proj` {type: "laea", lon0, lat0, x0, y0, s}.
* `land`: 152 strings, one per land polygon. Fill them (light), and stroke lightly if wanted.
  They are clipped a few pixels outside the frame, so no edge lines show.
* `borders`: 14 open polylines for international borders (US-Canada, US-Mexico, Central America, Caribbean). Stroke only.
* `states`: 120 open polylines for US interior state borders. Stroke only.
* `airports`: {CODE: [x, y]} for all 93 airports in `DATA_AIRLINE_REAL.network.airports`.

### `west`
* `viewBox`: "0 0 800 697". `proj` as above.
* `states`: 21 entries, each `{name, fleet, d}`. `fleet` is true for the 10 states that hold a
  fleet city. The others are neighbouring states whose centroid lies west of 89.5 W. Shapes are
  whole, not clipped, and shared borders were simplified once per arc, so neighbours meet exactly.
* `cities`: 27 entries, each `{city, state, x, y, pings, abnormal, rate}`. `rate` is abnormal
  events per 1,000 pings (`per_1000_pings`).

### `meta`
`source`, `projection`, `simplify_px` {pacific, west}, `pacific_airports_off_frame` (empty), `missing_states` (empty).
