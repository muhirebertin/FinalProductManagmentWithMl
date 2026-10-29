# analytics/ml/external.py
"""
Open API integration: live USD -> RWF exchange rate.

Source : ExchangeRate-API open access endpoint (no key required)
         https://open.er-api.com/v6/latest/USD
Policy : 1. serve from the in-memory cache when fresh (6 hours);
         2. otherwise call the Open API (5-second timeout);
         3. if the call fails, serve the last good value saved in the database;
         4. if there has never been a good value, serve a documented fallback.
The ERP therefore never breaks or slows down when there is no internet.
"""
import json
import logging
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("analytics")

FX_URL = "https://open.er-api.com/v6/latest/USD"
FX_CACHE_KEY = "analytics:fx:usd"
FX_TTL_SECONDS = 6 * 3600
FALLBACK_USD_RWF = 1450.0


def _fallback_rate():
    return float(getattr(settings, "AI_FALLBACK_USD_RWF", FALLBACK_USD_RWF))


def fetch_usd_rwf(force=False, timeout=5):
    from analytics.models import ExternalDataSnapshot

    if not force:
        cached = cache.get(FX_CACHE_KEY)
        if cached:
            return cached

    if getattr(settings, "AI_EXTERNAL_APIS_ENABLED", True):
        try:
            req = urllib.request.Request(FX_URL, headers={"User-Agent": "LeMieux-ERP/2.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("result") != "success" or "RWF" not in body.get("rates", {}):
                raise ValueError("Unexpected response format")
            data = {
                "base": "USD",
                "rate": round(float(body["rates"]["RWF"]), 2),
                "provider": "open.er-api.com (ExchangeRate-API)",
                "provider_updated": body.get("time_last_update_utc", ""),
                "fetched_at": timezone.now().isoformat(),
                "status": "live",
            }
            ExternalDataSnapshot.objects.update_or_create(
                key="fx_usd_rwf", defaults={"payload": data, "fetched_at": timezone.now()})
            cache.set(FX_CACHE_KEY, data, FX_TTL_SECONDS)
            return data
        except Exception as exc:  # network down, timeout, format change...
            logger.warning("Open API exchange-rate call failed: %s", exc)

    snap = ExternalDataSnapshot.objects.filter(key="fx_usd_rwf").first()
    if snap:
        data = dict(snap.payload)
        data["status"] = "cached"
    else:
        data = {"base": "USD", "rate": _fallback_rate(), "provider": "offline fallback (settings)",
                "provider_updated": "", "fetched_at": timezone.now().isoformat(), "status": "fallback"}
    cache.set(FX_CACHE_KEY, data, 15 * 60)  # retry the live API after 15 minutes
    return data
