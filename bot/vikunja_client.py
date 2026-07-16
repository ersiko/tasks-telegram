from datetime import datetime
from typing import Optional

import httpx


class VikunjaAPIError(Exception):
    pass


class VikunjaClient:
    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        self._token = token

    async def _request(self, method: str, path: str, **kwargs):
        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=15.0,
        ) as client:
            response = await client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise VikunjaAPIError(f"{method} {path} failed ({response.status_code}): {response.text[:200]}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def list_projects(self) -> list[dict]:
        return await self._request("GET", "/projects") or []

    async def resolve_project(self, name: str) -> Optional[dict]:
        projects = await self.list_projects()
        name_lower = name.lower()
        for project in projects:
            if project.get("title", "").lower() == name_lower:
                return project
        for project in projects:
            if name_lower in project.get("title", "").lower():
                return project
        return None

    async def list_tasks(self, project_id: Optional[int] = None, include_done: bool = False) -> list[dict]:
        # Filtering the global /tasks endpoint by project_id, rather than
        # using /projects/{id}/views/{view}/tasks, sidesteps a Vikunja
        # permission gap: that view-scoped endpoint 401s even with full
        # Tasks + Project Views permissions granted (confirmed live against
        # this instance) - a distinct, seemingly ungrantable permission.
        filters = []
        if not include_done:
            filters.append("done = false")
        if project_id is not None:
            filters.append(f"project_id = {project_id}")
        params = {"filter": " && ".join(filters)} if filters else {}
        return await self._request("GET", "/tasks", params=params) or []

    async def create_task(
        self,
        project_id: int,
        title: str,
        due_date: Optional[datetime] = None,
        priority: Optional[int] = None,
    ) -> dict:
        payload = {"title": title}
        if due_date is not None:
            payload["due_date"] = due_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        if priority is not None:
            payload["priority"] = priority
        return await self._request("PUT", f"/projects/{project_id}/tasks", json=payload)

    async def get_task(self, task_id: int) -> dict:
        return await self._request("GET", f"/tasks/{task_id}")

    async def set_done(self, task_id: int, done: bool = True) -> dict:
        return await self._request("POST", f"/tasks/{task_id}", json={"done": done})

    async def set_due_date(self, task_id: int, due_date: Optional[datetime]) -> dict:
        payload = {"due_date": due_date.strftime("%Y-%m-%dT%H:%M:%SZ") if due_date else None}
        return await self._request("POST", f"/tasks/{task_id}", json=payload)

    async def delete_task(self, task_id: int) -> None:
        await self._request("DELETE", f"/tasks/{task_id}")

    async def list_labels(self) -> list[dict]:
        return await self._request("GET", "/labels") or []

    async def resolve_label(self, name: str) -> dict:
        labels = await self.list_labels()
        name_lower = name.lower()
        for label in labels:
            if label.get("title", "").lower() == name_lower:
                return label
        return await self._request("PUT", "/labels", json={"title": name})

    async def add_label_to_task(self, task_id: int, label_id: int) -> None:
        await self._request("PUT", f"/tasks/{task_id}/labels", json={"label_id": label_id})
