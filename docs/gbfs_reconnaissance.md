# Rozpoznanie API GBFS MEVO

Data rozpoznania: 2026-08-12. Wszystkie zapytania wykonano jednorazowo z nagłówkiem:

> Ten dokument jest migawką źródła z podanej daty. Liczby rekordów, wartości pól i rozmiary odpowiedzi są przykładami punktowymi, a nie stałymi inwariantami działającego pipeline'u.

```text
Client-Identifier: s194586-mevo-analytics
```

## 1. Auto-discovery

`gbfs.json` jest plikiem auto-discovery GBFS: zawiera metadane publikacji oraz listę feedów wraz z ich aktualnymi adresami URL. Nie należy zakładać adresów feedów niezależnie od tego pliku.

Źródło: <https://gbfs.urbansharing.com/rowermevo.pl/gbfs.json>

- wersja GBFS: `2.3`
- `last_updated`: `1786488195` (czas Unix; bieżący snapshot został pobrany 2026-08-12)
- `ttl`: `15` sekund
- język: `pl`

Aktualne feedy:

| Feed | URL |
|---|---|
| `system_information` | <https://gbfs.urbansharing.com/rowermevo.pl/system_information.json> |
| `vehicle_types` | <https://gbfs.urbansharing.com/rowermevo.pl/vehicle_types.json> |
| `system_pricing_plans` | <https://gbfs.urbansharing.com/rowermevo.pl/system_pricing_plans.json> |
| `station_information` | <https://gbfs.urbansharing.com/rowermevo.pl/station_information.json> |
| `station_status` | <https://gbfs.urbansharing.com/rowermevo.pl/station_status.json> |
| `free_bike_status` | <https://gbfs.urbansharing.com/rowermevo.pl/free_bike_status.json> |

## 2. `station_information`

Feed zawiera 837 stacji. Wszystkie rekordy w sprawdzonym snapshotcie miały `is_virtual_station: true`.

Rzeczywiste pola rekordu:

```text
station_id, name, address, cross_street, lat, lon,
is_virtual_station, capacity, station_area, rental_uris
```

Występują między innymi: identyfikator, nazwa, adres, dodatkowy opis skrzyżowania, współrzędne, pojemność, geometria `station_area` oraz URI aplikacji. `rental_methods`, `vehicle_capacity` i `vehicle_type_capacity` nie wystąpiły w odpowiedzi (nie należy ich dopowiadać na podstawie ogólnej dokumentacji GBFS).

Przykład skrócony:

```json
{"station_id":"8260","name":"GTC001","lat":54.0511646436,"lon":18.8114399838,"capacity":10,"is_virtual_station":true}
```

## 3. `station_status`

Feed zawiera 837 rekordów, po jednym dla każdej stacji. Rzeczywiste pola:

```text
station_id, is_installed, is_renting, is_returning, last_reported,
num_vehicles_available, num_bikes_available, num_docks_available,
vehicle_types_available
```

`vehicle_types_available` zawiera identyfikator typu i liczność, np.:

```json
{"vehicle_type_id":"bike","count":1}
{"vehicle_type_id":"ebike","count":3}
```

Na tej podstawie można rozróżnić liczbę rowerów klasycznych i elektrycznych na stacji. W tym snapshotcie suma wynosiła odpowiednio 1009 `bike` i 2861 `ebike`. `num_bikes_available` jest zgodne z sumą typów dla analizowanego snapshotu.

## 4. `free_bike_status`

Feed zawiera 833 rekordy wolnostojących rowerów. Rzeczywiste pola:

```text
bike_id, lat, lon, is_reserved, is_disabled, rental_uris,
vehicle_type_id, last_reported, current_range_meters
```

W tym feedzie nie występuje `station_id`, więc roweru wolnostojącego nie można bezpośrednio przypisać do stacji na podstawie payloadu. Nie występują też pola `pricing_plan_id` ani `vehicle_docks_available`.

`current_range_meters` występuje w schemacie. W pobranym snapshotcie:

- 534/833 rekordów miało wartość niepustą;
- wszystkie 534 wartości dotyczyły `ebike`;
- 170 e-bike’ów miało wartość pustą;
- 129 klasycznych rowerów miało wartość pustą.

Zatem API udostępnia częściową informację o pozostałym zasięgu e-bike’a, ale nie gwarantuje jej dla każdego rekordu. Nie znaleziono osobnego pola z poziomem baterii.

## 5. `vehicle_types`

Występują dwa typy:

| `vehicle_type_id` | `form_factor` | `propulsion_type` | `name` | Dodatkowe pola |
|---|---|---|---|---|
| `bike` | `bicycle` | `human` | `Traditional bike` | `default_pricing_plan_id: bike`, `rider_capacity: 1` |
| `ebike` | `bicycle` | `electric_assist` | `Electric bike` | `default_pricing_plan_id: ebike`, `max_range_meters: 100000`, `rider_capacity: 1` |

`vehicle_type_id` jednoznacznie pozwala rozróżnić rower klasyczny (`bike`) i elektryczny (`ebike`).

## 6. `system_pricing_plans`

Występują plany `bike` i `ebike`. Pola rekordu to:

```text
plan_id, name, currency, price, description, is_taxable, per_min_pricing
```

Waluta to `PLN`, a `is_taxable` ma wartość `false` w obu sprawdzonych planach. Szczegółowa analiza cennika nie była częścią tego rozpoznania.

## 7. `system_information`

Istotne pola:

```text
system_id: inurba-gdansk
language: pl
name: MEVO
operator: Inurba
timezone: Europe/Warsaw
```

Feed zawiera również numer telefonu, e-mail oraz `rental_apps` dla Androida i iOS.

## 8. Relacje między feedami

- Wszystkie 837 `station_status.station_id` mają odpowiednik w `station_information.station_id`.
- Nie znaleziono brakujących ani nadmiarowych identyfikatorów stacji.
- `free_bike_status.vehicle_type_id` przyjmuje wartości `bike` i `ebike`; obie mają odpowiedniki w `vehicle_types.vehicle_type_id`.
- `free_bike_status` nie zawiera `station_id`, więc relacja wolnego roweru do stacji nie jest dostępna wprost.

## 9. Rozmiar i wolumen danych

Rozmiary oznaczają bajty treści JSON odpowiedzi, bez narzutów HTTP. Dla czytelności podano zarówno KB/MB dziesiętne, jak i przybliżone wartości binarne.

| Feed | Rekordy | Snapshot | 144 snapshoty/dzień | 30 dni |
|---|---:|---:|---:|---:|
| `station_status` | 837 | 260 002 B = 260.00 KB = 0.260 MB | 37.44 MB/dzień | 1.123 GB/miesiąc |
| `free_bike_status` | 833 | 296 310 B = 296.31 KB = 0.296 MB | 42.67 MB/dzień | 1.280 GB/miesiąc |
| **Razem** | — | **556 312 B = 556.31 KB = 0.556 MB** | **80.11 MB/dzień** | **2.403 GB/miesiąc** |

## 10. Wnioski dla collectora

1. Collector powinien najpierw pobierać `gbfs.json` i korzystać z feedów wskazanych w aktualnym payloadzie.
2. Każde żądanie powinno zawierać `Client-Identifier`; `ttl` wynosi obecnie 15 sekund.
3. Do klasyfikacji `bike`/`ebike` należy używać `vehicle_type_id` oraz walidować jego definicję przez `vehicle_types`.
4. Dla stacji można zapisywać liczby typów z `vehicle_types_available`; dla wolnych rowerów nie należy zakładać obecności `station_id`.
5. `current_range_meters` należy traktować jako pole opcjonalne i nullable. Nie należy wyliczać poziomu baterii z samego `max_range_meters`.
6. Należy przechowywać `last_reported` oraz czas pobrania snapshotu, aby odróżniać wiek danych od czasu wykonania collectora.
7. Podane rozmiary są wynikiem jednego snapshotu i mogą zmieniać się wraz z liczbą rekordów oraz długością geometrii `station_area`.
