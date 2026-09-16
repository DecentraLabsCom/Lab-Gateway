import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request


def create_aas_link_router(*, get_link_path: Any) -> APIRouter:
    router = APIRouter()

    async def read_link_request(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        raw_aas_id = body.get("aasId")
        aas_id = raw_aas_id.strip() if isinstance(raw_aas_id, str) else ""
        if not aas_id or len(aas_id) > 2048:
            raise HTTPException(status_code=400, detail="aasId is required")
        return {"aasId": aas_id}

    @router.post("/aas-admin/lab/{lab_id}/aas-link")
    async def create_lab_aas_link(lab_id: str, request: Request):
        """Link any laboratory resource to an externally-managed AAS shell."""
        link = await read_link_request(request)
        lab_key = str(lab_id or "").strip()
        if not lab_key:
            raise HTTPException(status_code=400, detail="labId is required")
        link["labId"] = lab_key
        fp = get_link_path(lab_key)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(link, indent=2), encoding="utf-8")
        return {"linked": True, **link}

    @router.get("/aas-admin/lab/{lab_id}/aas-link")
    async def get_lab_aas_link(lab_id: str):
        """Return the AAS link for a laboratory resource, or 404."""
        lab_key = str(lab_id or "").strip()
        fp = get_link_path(lab_key)
        if not fp.is_file():
            raise HTTPException(status_code=404, detail="No AAS link configured for this laboratory")
        try:
            link = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=500, detail="Corrupt AAS link file")
        return {"labId": lab_key, **link}

    @router.delete("/aas-admin/lab/{lab_id}/aas-link")
    async def delete_lab_aas_link(lab_id: str):
        """Remove the AAS link for a laboratory resource."""
        lab_key = str(lab_id or "").strip()
        fp = get_link_path(lab_key)
        if not fp.is_file():
            raise HTTPException(status_code=404, detail="No AAS link configured for this laboratory")
        fp.unlink()
        return {"unlinked": True, "labId": lab_key}

    @router.post("/aas-admin/fmu/{access_key}/aas-link")
    async def create_aas_link(access_key: str, request: Request):
        """
        Link an FMU access key to an externally-managed AAS shell.

        Body JSON: ``{"aasId": "<shell-id>", "labId": "<optional>", "submodelIds": ["<optional>"]}``

        ``labId`` should match the numeric on-chain lab ID used in the
        ``urn:decentralabs:lab:{labId}`` shell ID that the Marketplace queries.
        When provided the link is indexed by labId so OpenResty can resolve
        the conventional ID even though the ``accessKey`` is a different string
        (e.g. ``motor.fmu`` vs ``42``).

        The Gateway's ``/aas/`` proxy resolves requests for
        ``urn:decentralabs:lab:{labId}`` to the linked AAS ID transparently —
        Marketplace consumers need no changes.
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        aas_id = (body.get("aasId") or "").strip()
        if not aas_id:
            raise HTTPException(status_code=400, detail="aasId is required")
        lab_id = str(body.get("labId") or "").strip() or None
        link: dict = {"aasId": aas_id}
        if lab_id:
            link["labId"] = lab_id
        submodel_ids = body.get("submodelIds")
        if submodel_ids and isinstance(submodel_ids, list):
            link["submodelIds"] = [s.strip() for s in submodel_ids if isinstance(s, str) and s.strip()]
        fp = get_link_path(access_key)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(link, indent=2), encoding="utf-8")
        if lab_id and lab_id != access_key:
            fp_lab = get_link_path(lab_id)
            fp_lab.write_text(json.dumps(link, indent=2), encoding="utf-8")
        return {"linked": True, "accessKey": access_key, **link}

    @router.get("/aas-admin/fmu/{access_key}/aas-link")
    async def get_aas_link(access_key: str):
        """Return the current AAS link for a given access key, or 404."""
        fp = get_link_path(access_key)
        if not fp.is_file():
            raise HTTPException(status_code=404, detail="No AAS link configured for this access key")
        try:
            link = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=500, detail="Corrupt AAS link file")
        return {"accessKey": access_key, **link}

    @router.delete("/aas-admin/fmu/{access_key}/aas-link")
    async def delete_aas_link(access_key: str):
        """Remove the AAS link for a given access key."""
        fp = get_link_path(access_key)
        if not fp.is_file():
            raise HTTPException(status_code=404, detail="No AAS link configured for this access key")
        try:
            stored = json.loads(fp.read_text(encoding="utf-8"))
            lab_id = stored.get("labId", "")
        except Exception:
            lab_id = ""
        fp.unlink()
        if lab_id and lab_id != access_key:
            fp_lab = get_link_path(lab_id)
            if fp_lab.is_file():
                fp_lab.unlink()
        return {"unlinked": True, "accessKey": access_key}

    @router.get("/aas-admin/resolve-aas-id")
    async def resolve_aas_id(shellId: str = Query(...)):
        """
        Resolve a conventional AAS shell ID to the actual target ID.

        Called by OpenResty (Lua subrequest) before proxying ``/aas/`` to BaSyx.
        If an AAS link override exists for the lab ID embedded in the shell ID,
        the response contains the overridden ``targetId``; otherwise returns the
        original ``shellId`` unchanged.

        Query param ``shellId`` is the base64url-decoded shell ID string,
        e.g. ``urn:decentralabs:lab:42``.
        """
        prefix = "urn:decentralabs:lab:"
        if not shellId.startswith(prefix):
            return {"targetId": shellId, "override": False}

        lab_key = shellId[len(prefix):]
        fp = get_link_path(lab_key)
        if fp.is_file():
            try:
                link = json.loads(fp.read_text(encoding="utf-8"))
                target = link.get("aasId", "").strip()
                if target:
                    return {"targetId": target, "override": True}
            except Exception:
                pass

        fp_fmu = get_link_path(f"{lab_key}.fmu")
        if fp_fmu.is_file():
            try:
                link = json.loads(fp_fmu.read_text(encoding="utf-8"))
                target = link.get("aasId", "").strip()
                if target:
                    return {"targetId": target, "override": True}
            except Exception:
                pass

        return {"targetId": shellId, "override": False}

    return router
