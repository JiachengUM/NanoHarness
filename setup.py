from setuptools import setup, find_packages

# 读取 README 文件
try:
    with open("README.md", encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = ""

# 核心依赖（手动指定，避免 requirements.txt 编码问题）
install_requires = [
    "openai>=1.0.0",
    "pydantic>=2.0.0",
    "fastapi>=0.100.0",
    "pandas>=1.5.0",
]

setup(
    name="nanoai",
    version="0.1.0",
    author="yitu",
    author_email="your@email.com",
    description="Nano AI - 精细小巧灵活的 AI 组件和 demo 库",
    long_description=long_description,
    long_description_content_type="text/markdown",

    # 包发现配置
    packages=find_packages(),
    include_package_data=True,
    
    # Python 版本要求
    python_requires=">=3.12",
    
    # 依赖项（从 requirements.txt 读取）
    install_requires=install_requires,

    # 分类信息
    classifiers=[
        "Programming Language :: Python :: 3.12",
    ],
)

