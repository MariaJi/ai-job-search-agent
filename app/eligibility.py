"""Conservative search eligibility, independent of source verification and fit."""

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field


# Supported ISO 3166-1 alpha-2 codes. Unknown values must not become exclusions.
SUPPORTED_COUNTRY_CODES = frozenset("""
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP
KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY
MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY
QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ
VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
""".split())
COUNTRY_ALIASES = {"UK": "GB"}


def normalize_country_codes(values: object) -> set[str] | None:
    """None means ambiguous input, including partially unsupported lists."""
    if not isinstance(values, list):
        return None
    normalized = set()
    for value in values:
        if not isinstance(value, str):
            return None
        code = value.strip().upper()
        code = COUNTRY_ALIASES.get(code, code)
        if code not in SUPPORTED_COUNTRY_CODES:
            return None
        normalized.add(code)
    return normalized


class SearchConstraints(BaseModel):
    remote_required: bool = False
    geography: str = ""
    geography_scope: Literal["country", "subnational", "unknown"] = "unknown"
    country_codes: list[str] = Field(default_factory=list)
    recency_days: int | None = Field(default=None, ge=1)


class VerifiedConstraintsEvidence(BaseModel):
    work_arrangement: Literal["remote", "hybrid", "in_office", "unknown"] = "unknown"
    # Countries must describe the complete permitted applicant/workplace set,
    # never a headquarters address or a merely illustrative office list.
    country_codes: list[str] = Field(default_factory=list)
    countries_exhaustive: bool = False
    posting_date: str | None = None
    posting_age_days: int | None = Field(default=None, ge=0)


def assess_eligibility(constraints: dict, evidence: dict) -> dict:
    checks = {"remote": "unknown", "geography": "unknown", "recency": "unknown"}
    facts = evidence.get("facts", {})
    if constraints.get("remote_required"):
        arrangement = facts.get("work_arrangement")
        if arrangement == "remote":
            checks["remote"] = "compatible"
        elif arrangement in ("hybrid", "in_office"):
            checks["remote"] = "contradicted"

    requested = normalize_country_codes(constraints.get("country_codes", []))
    permitted = normalize_country_codes(facts.get("country_codes", []))
    if requested and permitted and facts.get("countries_exhaustive"):
        if requested.isdisjoint(permitted):
            checks["geography"] = "contradicted"
        elif not constraints.get("geography") or constraints.get("geography_scope") == "country":
            checks["geography"] = "compatible"

    days = constraints.get("recency_days")
    if days is not None:
        try:
            observed = datetime.fromisoformat(evidence["observed_at"]).date()
            dates = []
            posted = facts.get("posting_date")
            if posted:
                dates.append(date.fromisoformat(posted))
            age = facts.get("posting_age_days")
            if type(age) is int and age >= 0:
                dates.append(observed - timedelta(days=age))
            # Conflicting/future evidence is unknown. Date-only cutoff is inclusive.
            if dates and len(set(dates)) == 1 and dates[0] <= observed:
                checks["recency"] = "contradicted" if dates[0] < observed - timedelta(days=days) else "compatible"
        except (KeyError, TypeError, ValueError, OverflowError):
            pass

    active = ([checks["remote"]] if constraints.get("remote_required") else [])
    if constraints.get("geography") or constraints.get("country_codes"):
        active.append(checks["geography"])
    if days is not None:
        active.append(checks["recency"])
    status = ("contradicted" if "contradicted" in active else
              "compatible" if active and all(value == "compatible" for value in active) else "unknown")
    return {"status": status, "checks": checks}
