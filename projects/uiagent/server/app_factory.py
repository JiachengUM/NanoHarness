import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from projects.uiagent.server.configs.config import AppConfig
from projects.uiagent.server.configs.nacos_configs import NacosConfigs
from projects.uiagent.server.configs.init_database import init_engine, close_db
from projects.uiagent.server.controller.common_controller import register_routes
from projects.uiagent.server.controller.gui_controller import GUIController, gui_router

from projects.uiagent.server.controller.health_controller import (
    HealthController,
    health_router,
)
from projects.uiagent.server.middlewares.log import register_request_save
from projects.uiagent.server.models.log import LogTable
from projects.uiagent.server.utils.redis_util import RedisUtil

logger = logging.getLogger(__name__)


async def create_app() -> FastAPI:
    app = FastAPI(title="UI-AGENT-API", description="ui-agent-API", version="0.1.0")
    # CORS 设置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 初始化数据库和服务
    @app.on_event("startup")
    async def on_startup():
        await NacosConfigs.init()
        await AppConfig.init()
        await init_engine(AppConfig.DATABASE_URL)

        app.state.redis_client = RedisUtil(
            host=AppConfig.REDIS_HOST,
            port=AppConfig.REDIS_PORT,
            db=AppConfig.REDIS_DB,
            password=AppConfig.REDIS_PASSWORD,
            decode_responses=True,
        )

        _setup_routes()

        logger.info("ui-agent服务初始化完成")

    # 应用关闭时清理资源
    @app.on_event("shutdown")
    async def on_shutdown():
        await close_db()
        logger.info("ui-agent服务关闭完成")

    def _setup_routes():
        # 注册接口
        # 健康检查
        route_health_controller = HealthController()
        health_router.get("/health")(route_health_controller.health_check)
        app.include_router(health_router)

        # 出入参查询
        app.post("/log", description="form格式入参，参数为trace_id、chat_id必须有其一")(LogTable.get_log_data)

        # ui agent
        route_gui_controller = GUIController()
        gui_router.post("/gui_nl_only")(route_gui_controller.gui_nl_only)
        gui_router.post("/gui_image_only")(route_gui_controller.gui_image_only)
        gui_router.post("/gui_nl_only_test")(route_gui_controller.gui_nl_only_test)
        gui_router.post("/gui_image_only_test")(route_gui_controller.gui_image_only_test)

        gui_router.post("/seatbooking_mini_nl_only")(route_gui_controller.seatbooking_mini_nl_only)
        gui_router.post("/seatbooking_mini_image_only")(route_gui_controller.seatbooking_mini_image_only)
        gui_router.post("/seatbooking_mini_nl_only_test")(route_gui_controller.seatbooking_mini_nl_only_test)
        gui_router.post("/seatbooking_mini_image_only_test")(route_gui_controller.seatbooking_mini_image_only_test)

        gui_router.post("/coffee_purchase_nl_only")(route_gui_controller.coffee_purchase_nl_only)
        gui_router.post("/coffee_purchase_image_only")(route_gui_controller.coffee_purchase_image_only)
        gui_router.post("/coffee_purchase_nl_only_test")(route_gui_controller.coffee_purchase_nl_only_test)
        gui_router.post("/coffee_purchase_image_only_test")(route_gui_controller.coffee_purchase_image_only_test)

        gui_router.post("/movie_ticket_booking_nl_only")(route_gui_controller.movie_ticket_booking_nl_only)
        gui_router.post("/movie_ticket_booking_image_only")(route_gui_controller.movie_ticket_booking_image_only)
        gui_router.post("/movie_ticket_booking_nl_only_test")(route_gui_controller.movie_ticket_booking_nl_only_test)
        gui_router.post("/movie_ticket_booking_image_only_test")(route_gui_controller.movie_ticket_booking_image_only_test)

        app.include_router(gui_router)


    # 通用出入参存数据库中间件
    register_request_save(app)
    # 注册所有接口 必须放在最后 最先生效
    register_routes(app)

    return app
