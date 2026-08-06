from req2test.retrieval import LocalRuleRetriever


def test_retriever_returns_relevant_section():
    retriever = LocalRuleRetriever(
        [
            "## 登录测试\n验证账号密码和登录失败提示。",
            "## 文件上传\n验证文件格式和大小限制。",
            "## 查询测试\n验证筛选条件和空结果。",
        ]
    )
    result = retriever.retrieve("上传不支持格式的文件", top_k=1)
    assert "文件上传" in result[0]
