"""Exercise a disposable deployment. Creates a test user, task and evaluation."""

import argparse
import json
import secrets
import uuid

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--execution-base-url", help="Server-side URL when Docker maps ports")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=180) as client:
        for path, expected in [("/health", 200), ("/ready", 200),
                               ("/workbench", 307), ("/register", 200), ("/demo", 200)]:
            response = client.get(path)
            assert response.status_code == expected, (path, response.status_code)
            print(path, response.status_code)
        credentials = {"email": f"render-smoke-{uuid.uuid4().hex}@example.test",
                       "password": secrets.token_urlsafe(24)}
        response = client.post("/api/v1/auth/register", json=credentials)
        assert response.status_code == 201, response.text
        response = client.post("/api/v1/auth/login", json=credentials)
        assert response.status_code == 200, response.text
        assert "secure" in response.headers["set-cookie"].lower()
        token = response.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        # Plain localhost HTTP won't send a Secure cookie automatically.
        response = client.get("/workbench", headers={"Cookie": f"req2test_access_token={token}"})
        assert response.status_code == 200
        print("register/login/secure-cookie/authenticated-workbench OK")
        response = client.post("/api/v1/knowledge/search", json={"query": "认证失败 token", "top_k": 3})
        assert response.status_code == 200 and response.json()["items"], response.text
        print("knowledge search OK")
        response = client.post("/api/v1/tasks", json={
            "requirement_text": '# 状态查询\nGET /demo-target/health 状态码: 200 响应包含: {"status":"ok"}',
            "generation_config": {"max_cases": 3},
            "execution_config": {"enabled": True, "base_url": args.execution_base_url or args.base_url,
                                 "max_executable_cases": 1, "use_llm_planner": False,
                                 "api_specs": [{"case_id": "smoke", "name": "health",
                                                "path": "/demo-target/health"}]},
        })
        assert response.status_code == 202, response.text
        task_url = response.json()["status_url"]
        task = client.get(task_url).json()
        assert task["status"] == "completed", task.get("error")
        assert task["result"]["test_cases"]
        execution = task["result"]["execution"]
        assert execution["enabled"]
        assert execution["summary"]["http_pass_rate"] == 1.0, execution["summary"]
        assert execution["summary"]["pytest_passed"] is True, execution["summary"]
        print("eager task + execution OK", json.dumps(execution["summary"], ensure_ascii=False))
        datasets = client.get("/api/v1/evaluations/datasets").json()["items"]
        assert datasets
        response = client.post("/api/v1/evaluations/runs", json={"dataset_name": datasets[0]["name"]})
        assert response.status_code == 202, response.text
        evaluation_url = response.json()["status_url"]
        evaluation = client.get(evaluation_url).json()
        assert evaluation["status"] == "completed", evaluation
        print("eager evaluation OK")
        print(json.dumps({"task_url": task_url, "evaluation_url": evaluation_url}))


if __name__ == "__main__":
    main()
