"""Async FHIR R4 read client used by the API routes."""

import asyncio
import os

import httpx
from fastapi import HTTPException

DEFAULT_BASE_URL = "https://hapi.fhir.org/baseR4"
MAX_RESOURCES = 200

CHART_RESOURCE_TYPES = [
    "DocumentReference",
    "DiagnosticReport",
    "MedicationRequest",
    "AllergyIntolerance",
    "CarePlan",
    "Goal",
    "Consent",
    "CareTeam",
    "ServiceRequest",
    "Task",
    "Condition",
    "Encounter",
]


class FhirClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("FHIR_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=30,
            headers={"Accept": "application/fhir+json"},
        )

    @staticmethod
    def _entry_resources(bundle: dict) -> list[dict]:
        return [e["resource"] for e in bundle.get("entry", []) if e.get("resource")]

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            async with self._client() as client:
                resp = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"FHIR server unreachable at {self.base_url}: {exc}",
            ) from exc
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                detail = resp.json()
            except ValueError:
                pass
            raise HTTPException(status_code=resp.status_code,
                                detail={"fhir_error": detail})
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    async def get(self, resource_type: str, id: str) -> dict:
        return await self._request("GET", f"{self.base_url}/{resource_type}/{id}")

    async def search(self, resource_type: str, **params) -> list[dict]:
        """Search a resource type, following `next` links, capped at MAX_RESOURCES."""
        url = f"{self.base_url}/{resource_type}"
        resources: list[dict] = []
        while url and len(resources) < MAX_RESOURCES:
            bundle = await self._request("GET", url, params=params or None)
            resources.extend(self._entry_resources(bundle))
            params = {}  # params only apply to the first request
            url = next(
                (link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"),
                None,
            )
            if url and not url.startswith("http"):
                url = f"{self.base_url}/{url.lstrip('/')}"
        return resources[:MAX_RESOURCES]

    @staticmethod
    def _check_output_id(id: str) -> None:
        if not id.startswith("baton-out-"):
            raise ValueError(f"refusing to write resource id without baton-out- prefix: {id}")

    async def create(self, resource_type: str, resource: dict) -> dict:
        return await self._request(
            "POST", f"{self.base_url}/{resource_type}", json=resource,
            headers={"Content-Type": "application/fhir+json"})

    async def put(self, resource_type: str, id: str, resource: dict) -> dict:
        self._check_output_id(id)
        return await self._request(
            "PUT", f"{self.base_url}/{resource_type}/{id}", json=resource,
            headers={"Content-Type": "application/fhir+json"})

    async def delete(self, resource_type: str, id: str) -> None:
        self._check_output_id(id)
        try:
            await self._request("DELETE", f"{self.base_url}/{resource_type}/{id}")
        except HTTPException as exc:
            if exc.status_code not in (404, 410):
                raise

    async def patient_chart(self, patient_id: str) -> dict[str, list[dict] | dict]:
        patient, *results = await asyncio.gather(
            self.get("Patient", patient_id),
            *(
                self.search(rt, patient=patient_id, _count=100)
                for rt in CHART_RESOURCE_TYPES
            ),
        )
        chart: dict[str, list[dict] | dict] = {"Patient": patient}
        chart.update(dict(zip(CHART_RESOURCE_TYPES, results)))
        return chart
