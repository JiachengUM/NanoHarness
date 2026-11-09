# GenericEval Architecture

This document explains the project structure and core design principles for developers.

## 📂 Project Structure

genericeval/
├── README.md
├── ARCHITECTURE.md
├── pyproject.toml
├── LICENSE
│
├── genericeval/
│   ├── __init__.py
│   │
│   ├── models/                  # 纯业务模型（无数据库依赖）
│   │   ├── __init__.py
│   │   ├── base.py              # InputBase[T], OutputBase[T], GroundTruthBase[T]
│   │   └── tasks.py             # TextX, ImageX, ClassificationY, etc.
│   │
│   ├── documents/               # Beanie Document 模型（持久层）
│   │   ├── __init__.py
│   │   ├── dataset.py           # Dataset, DatasetInputLink
│   │   ├── input.py             # TextInputDoc, ImageInputDoc
│   │   ├── annotation.py        # TextAnnotationDoc, ImageAnnotationDoc
│   │   ├── model_run.py         # TextModelRunDoc, ImageModelRunDoc (+ Prediction)
│   │   └── evaluation.py        # SampleEvalDoc, DatasetEvalDoc
│   │
│   ├── repositories/            # 数据访问层（Repository）
│   │   ├── __init__.py
│   │   └── run_result_repo.py   # TextRunResultRepository, etc.
│   │
│   ├── services/                # 业务逻辑层（Service）
│   │   ├── __init__.py
│   │   └── run_result_service.py  # TextRunResultService
│   │
│   ├── api/                     # FastAPI 接口
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app factory
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── inputs.py
│   │       ├── runs.py
│   │       └── evals.py
│   │
│   └── core/                    # 核心初始化与配置
│       ├── __init__.py
│       └── database.py          # init_beanie setup
│
└── tests/
    ├── __init__.py
    ├── conftest.py              # pytest fixture (MongoDB setup, DB isolation)
    ├── test_model_run.py        # 集成测试
    └── unit/
        ├── __init__.py
        └── test_run_result_service.py  # 单元测试（mock repository）
