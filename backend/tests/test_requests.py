"""Requests no page sends: numbers that JSON can't write back or the database can't
hold are refused plainly, wherever they arrive, rather than failing as an HTTP 500."""

from __future__ import annotations

import pytest

CUSTOMERS = "/api/customers"
STYLES = "/api/styles"
HUGE = 10 ** 30


@pytest.fixture
def customer(client, admin):
    _, headers = admin
    return client.post(CUSTOMERS, headers=headers, json={"name": "Fjordvik Logistik A/S"}).json()


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_a_number_that_isnt_one_is_refused_as_any_wrong_value_is(client, admin, customer,
                                                                 number) -> None:
    """The answer repeats what was sent, and JSON has no NaN or Infinity to repeat."""
    _, headers = admin
    json_headers = {**headers, "Content-Type": "application/json"}
    margins = client.patch(
        f"{CUSTOMERS}/{customer['id']}/background", headers=json_headers,
        content=f'{{"top": {number}, "bottom": 25, "left": 20, "right": 20}}')
    assert margins.status_code == 422
    [problem] = margins.json()["detail"]
    assert problem["loc"] == ["body", "top"]
    assert problem["input"] == number.lower().replace("infinity", "inf")

    style = client.post(STYLES, headers=headers, json={"name": "Nordlys brand"}).json()
    saved = client.put(
        f"{STYLES}/{style['id']}", headers=json_headers,
        content=f'{{"name": "Nordlys brand", "content": {{"sizes": {{"body": {number}}}}}, '
                f'"version": 1, "unknown": [{number}]}}')
    assert saved.status_code == 422
    assert saved.json()["detail"][0]["loc"] == ["body", "content", "sizes", "body"]
    assert client.get(f"{STYLES}/{style['id']}", headers=headers).json()["version"] == 1


def test_an_id_too_large_for_the_database_is_refused(client, admin, customer, session) -> None:
    _, headers = admin
    answers = [
        client.get(f"{CUSTOMERS}/{HUGE}", headers=headers),
        client.get(f"{CUSTOMERS}/-{HUGE}", headers=headers),
        client.get(f"{STYLES}/{HUGE}", headers=headers),
        client.delete(f"{STYLES}/{HUGE}", headers=headers),
        client.put(f"/api/custom-fields/{HUGE}", headers=headers, json={"label": "Tier"}),
        client.post(STYLES, headers=headers, json={"name": "Theirs", "customer_id": HUGE}),
        client.post(STYLES, headers=headers, json={
            "name": "Theirs", "customer_id": customer["id"], "based_on": HUGE}),
        client.put(f"{STYLES}/company-default", headers=headers, json={"style_id": HUGE}),
    ]
    for answer in answers:
        assert answer.status_code == 400, answer.request.url
        assert answer.json() == {"detail": "A number in the request is too large."}
    # Nothing of the refused requests was kept, and signing in still comes first.
    assert client.get(STYLES, headers=headers).json() == []
    assert client.get(f"{STYLES}/{HUGE}").status_code == 401
