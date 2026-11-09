import nest_asyncio
import streamlit as st
from typing import Any, Optional

from beanie import PydanticObjectId

from projects.mind.advisor.task_mdb_models.advisor_input import AdvisorInputDoc
from projects.mind.advisor.task_mdb_models.advisor_dataset import AdvisorDatasetDoc

from projects.mind.advisor.demo_dummy.streamlit_utils import get_db_client, run_async


async def create_dataset(name: str, description: Optional[str] = None) -> AdvisorDatasetDoc:
    '''
    创建新数据集
    
    参数:
        name: 数据集名称
        description: 数据集描述（可选）
        
    返回:
        AdvisorDatasetDoc: 创建的数据集文档对象
    '''
    dataset = AdvisorDatasetDoc(name=name, description=description)
    await dataset.insert()
    return dataset


async def get_dataset(dataset_id: str) -> Optional[AdvisorDatasetDoc]:
    '''
    获取数据集
    
    参数:
        dataset_id: 数据集 ID
        
    返回:
        Optional[AdvisorDatasetDoc]: 数据集文档对象，如果不存在则返回 None
    '''
    return await AdvisorDatasetDoc.get(dataset_id)


async def update_dataset(dataset_id: str, name: str, description: Optional[str] = None) -> Optional[AdvisorDatasetDoc]:
    '''
    更新数据集
    
    参数:
        dataset_id: 数据集 ID
        name: 新的名称
        description: 新的描述（可选）
        
    返回:
        Optional[AdvisorDatasetDoc]: 更新后的数据集文档，如果数据集不存在则返回 None
    '''
    dataset = await AdvisorDatasetDoc.get(dataset_id)
    if dataset:
        dataset.name = name
        dataset.description = description
        await dataset.save()
        return dataset
    return None


async def list_datasets() -> list[AdvisorDatasetDoc]:
    '''
    列出所有数据集
    
    返回:
        list[AdvisorDatasetDoc]: 数据集列表
    '''
    return await AdvisorDatasetDoc.find_all().to_list()


async def count_inputs_by_dataset(dataset_id: str) -> int:
    '''
    统计指定数据集的输入数据数量
    
    参数:
        dataset_id: 数据集 ID
        
    返回:
        int: 输入数据数量
    '''
    return await AdvisorInputDoc.find(AdvisorInputDoc.dataset_id == PydanticObjectId(dataset_id)).count()


async def create_input(event: str, context: str, dataset_id: Optional[str] = None) -> AdvisorInputDoc:
    '''
    创建新输入数据
    
    参数:
        event: 事件内容
        context: 工作环境上下文
        dataset_id: 所属数据集 ID（可选）
        
    返回:
        AdvisorInputDoc: 创建的输入数据文档对象
    '''
    dataset_obj_id = PydanticObjectId(dataset_id) if dataset_id else None
    input_doc = AdvisorInputDoc(event=event, context=context, dataset_id=dataset_obj_id)
    await input_doc.insert()
    return input_doc


async def get_input(input_id: str) -> Optional[AdvisorInputDoc]:
    '''
    获取输入数据
    
    参数:
        input_id: 输入数据 ID
        
    返回:
        Optional[AdvisorInputDoc]: 输入数据文档对象，如果不存在则返回 None
    '''
    return await AdvisorInputDoc.get(input_id)


async def update_input(input_id: str, event: str, context: str, dataset_id: Optional[str] = None) -> Optional[AdvisorInputDoc]:
    '''
    更新输入数据
    
    参数:
        input_id: 输入数据 ID
        event: 新的事件内容
        context: 新的工作环境上下文
        dataset_id: 新的所属数据集 ID（可选）
        
    返回:
        Optional[AdvisorInputDoc]: 更新后的输入数据文档，如果输入数据不存在则返回 None
    '''
    input_doc = await AdvisorInputDoc.get(input_id)
    if input_doc:
        input_doc.event = event
        input_doc.context = context
        input_doc.dataset_id = PydanticObjectId(dataset_id) if dataset_id else None
        await input_doc.save()
        return input_doc
    return None


async def delete_input(input_id: str) -> bool:
    '''
    删除输入数据
    
    参数:
        input_id: 输入数据 ID
        
    返回:
        bool: 删除是否成功
    '''
    input_doc = await AdvisorInputDoc.get(input_id)
    if input_doc:
        await input_doc.delete()
        return True
    return False


async def list_inputs(dataset_id: Optional[str] = None) -> list[AdvisorInputDoc]:
    '''
    列出输入数据
    
    参数:
        dataset_id: 数据集 ID（可选），如果提供则只返回该数据集的输入数据
        
    返回:
        list[AdvisorInputDoc]: 输入数据列表
    '''
    if dataset_id:
        return await AdvisorInputDoc.find(AdvisorInputDoc.dataset_id == PydanticObjectId(dataset_id)).to_list()
    return await AdvisorInputDoc.find_all().to_list()


def render_dataset_list(datasets: list[AdvisorDatasetDoc]) -> None:
    '''
    渲染数据集列表
    
    显示所有数据集的详细信息，包括名称、描述、输入数据数量、创建时间、更新时间。
    提供刷新按钮和数据集总数统计。
    '''
    if st.button("🔄 刷新列表", use_container_width=True, key="refresh_dataset_list"):
        st.rerun()

    if not datasets:
        st.info("暂无数据集数据")
        return

    dataset_data: list[dict[str, Any]] = []
    for dataset in datasets:
        input_count = run_async(count_inputs_by_dataset(str(dataset.id)))
        dataset_data.append({
            "名称": dataset.name,
            "描述": dataset.description or "-",
            "输入数据数量": input_count,
            "创建时间": dataset.created_time.strftime("%Y-%m-%d %H:%M:%S") if dataset.created_time else "-",
            "更新时间": dataset.updated_time.strftime("%Y-%m-%d %H:%M:%S") if dataset.updated_time else "-"
        })

    st.dataframe(
        dataset_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "名称": st.column_config.TextColumn("名称", width="medium"),
            "描述": st.column_config.TextColumn("描述", width="large"),
            "输入数据数量": st.column_config.NumberColumn("输入数据数量", width="small"),
            "创建时间": st.column_config.DatetimeColumn("创建时间", width="medium"),
            "更新时间": st.column_config.DatetimeColumn("更新时间", width="medium")
        }
    )


def render_create_dataset_form() -> None:
    '''
    渲染创建数据集表单
    
    提供名称、描述输入字段，提交后创建新数据集。
    '''
    with st.form("create_dataset_form"):
        name = st.text_input("名称 *", key="create_dataset_name")
        description = st.text_area("描述（可选）", key="create_dataset_description")
        
        submitted = st.form_submit_button("✅ 创建数据集", use_container_width=True, key="create_dataset_submit")
        
        if submitted:
            if not name:
                st.error("请填写数据集名称")
            else:
                try:
                    dataset = run_async(create_dataset(name, description if description else None))
                    st.success(f"✅ 数据集创建成功！ID: {dataset.id}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 创建失败: {str(e)}")


def render_edit_dataset_form(datasets: list[AdvisorDatasetDoc]) -> None:
    '''
    渲染编辑数据集表单
    
    参数:
        datasets: 数据集列表，用于生成选择下拉框
        
    提供数据集选择、名称、描述编辑字段，支持更新操作。
    '''
    if not datasets:
        st.info("暂无数据集数据，请先创建数据集")
        return
    
    dataset_options = {str(d.id): d.name for d in datasets}
    selected_dataset_id = st.selectbox("选择数据集", list(dataset_options.keys()), format_func=lambda x: dataset_options[x], key="edit_dataset_select")
    
    if not selected_dataset_id:
        return
    
    selected_dataset = run_async(get_dataset(selected_dataset_id))
    
    if not selected_dataset:
        return
    
    with st.form(f"edit_dataset_form_{selected_dataset_id}"):
        name = st.text_input("名称 *", value=selected_dataset.name, key=f"edit_dataset_name_{selected_dataset_id}")
        description = st.text_area("描述（可选）", value=selected_dataset.description or "", key=f"edit_dataset_description_{selected_dataset_id}")
        
        update_submitted = st.form_submit_button("✏️ 更新数据集", use_container_width=True, key=f"update_dataset_submit_{selected_dataset_id}")
        
        if update_submitted:
            if not name:
                st.error("请填写数据集名称")
            else:
                try:
                    dataset = run_async(update_dataset(
                        selected_dataset_id,
                        name,
                        description if description else None
                    ))
                    st.success(f"✅ 数据集更新成功！")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 更新失败: {str(e)}")


def render_input_list(inputs: list[AdvisorInputDoc], datasets: list[AdvisorDatasetDoc]) -> None:
    '''
    渲染输入数据列表
    
    参数:
        inputs: 输入数据列表
        datasets: 数据集列表，用于显示数据集名称
        
    显示所有输入数据的详细信息，包括事件、所属数据集名称、创建时间、更新时间。
    提供刷新按钮和按数据集筛选功能。
    '''
    if st.button("🔄 刷新列表", use_container_width=True, key="refresh_input_list"):
        st.rerun()

    dataset_filter_options = {"全部": None}
    for dataset in datasets:
        if dataset.id:
            dataset_filter_options[dataset.name] = str(dataset.id)
    
    selected_filter = st.selectbox("按数据集筛选", list(dataset_filter_options.keys()), key="input_dataset_filter")
    selected_dataset_id = dataset_filter_options[selected_filter]
    
    filtered_inputs = inputs
    if selected_dataset_id:
        filtered_inputs = [inp for inp in inputs if str(inp.dataset_id) == selected_dataset_id]

    if not filtered_inputs:
        st.info("暂无输入数据")
        return

    dataset_name_map = {str(d.id): d.name for d in datasets}
    
    input_data: list[dict[str, Any]] = []
    for input_doc in filtered_inputs:
        event_text = input_doc.event if isinstance(input_doc.event, str) else str(input_doc.event)
        if len(event_text) > 50:
            event_display = event_text[:50] + "..."
        else:
            event_display = event_text
        
        dataset_name = dataset_name_map.get(str(input_doc.dataset_id), "-") if input_doc.dataset_id else "-"
        
        input_data.append({
            "事件": event_display,
            "所属数据集": dataset_name,
            "创建时间": input_doc.created_time.strftime("%Y-%m-%d %H:%M:%S") if input_doc.created_time else "-",
            "更新时间": input_doc.updated_time.strftime("%Y-%m-%d %H:%M:%S") if input_doc.updated_time else "-"
        })

    st.dataframe(
        input_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "事件": st.column_config.TextColumn("事件", width="large"),
            "所属数据集": st.column_config.TextColumn("所属数据集", width="medium"),
            "创建时间": st.column_config.DatetimeColumn("创建时间", width="medium"),
            "更新时间": st.column_config.DatetimeColumn("更新时间", width="medium")
        }
    )


def render_create_input_form(datasets: list[AdvisorDatasetDoc]) -> None:
    '''
    渲染创建输入数据表单（结构化模式）
    
    参数:
        datasets: 数据集列表，用于生成选择下拉框
        
    提供事件、工作环境上下文（结构化）输入字段，支持选择所属数据集。
    使用 expander 提供工作环境上下文的各个字段编辑功能。
    '''
    dataset_options = {"无": None}
    for dataset in datasets:
        if dataset.id:
            dataset_options[dataset.name] = str(dataset.id)
    
    with st.expander("🔧 工作环境上下文（可选）"):
        st.markdown("编辑工作环境上下文的各个字段")
        
        user = st.text_area("用户画像（可选）", key="create_context_user")
        memory = st.text_area("记忆（可选）", key="create_context_memory")
        vehicle_state = st.text_area("车辆状态（可选）", key="create_context_vehicle_state")
        visual_exterior = st.text_area("外部视觉信息（可选）", key="create_context_visual_exterior")
        visual_interior = st.text_area("内部视觉信息（可选）", key="create_context_visual_interior")
        world_info = st.text_area("世界信息（可选）", key="create_context_world_info")
    
    with st.form("create_input_form"):
        event = st.text_area("事件 *", key="create_input_event", height=150)
        dataset_name = st.selectbox("所属数据集（可选）", list(dataset_options.keys()), key="create_input_dataset")
        
        submitted = st.form_submit_button("✅ 创建输入数据", use_container_width=True, key="create_input_submit")
        
        if submitted:
            if not event:
                st.error("请填写事件内容")
            else:
                try:
                    context_parts = []
                    if user:
                        context_parts.append(f"user: {user}")
                    if memory:
                        context_parts.append(f"memory: {memory}")
                    if vehicle_state:
                        context_parts.append(f"vehicle_state: {vehicle_state}")
                    if visual_exterior:
                        context_parts.append(f"visual_exterior: {visual_exterior}")
                    if visual_interior:
                        context_parts.append(f"visual_interior: {visual_interior}")
                    if world_info:
                        context_parts.append(f"world_info: {world_info}")
                    
                    context = "\n".join(context_parts) if context_parts else ""
                    
                    dataset_id = dataset_options[dataset_name]
                    input_doc = run_async(create_input(event, context, dataset_id))
                    st.success(f"✅ 输入数据创建成功！ID: {input_doc.id}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 创建失败: {str(e)}")


def render_edit_input_form(inputs: list[AdvisorInputDoc], datasets: list[AdvisorDatasetDoc]) -> None:
    '''
    渲染编辑输入数据表单（结构化模式，包括删除）
    
    参数:
        inputs: 输入数据列表，用于生成选择下拉框
        datasets: 数据集列表，用于生成数据集选择下拉框
        
    提供输入数据选择、事件、工作环境上下文（结构化）编辑字段，支持更新和删除操作。
    使用 expander 提供工作环境上下文的各个字段编辑功能。
    '''
    if not inputs:
        st.info("暂无输入数据，请先创建输入数据")
        return
    
    dataset_options = {"无": None}
    for dataset in datasets:
        if dataset.id:
            dataset_options[dataset.name] = str(dataset.id)
    
    input_options = {}
    for inp in inputs:
        event_text = inp.event if isinstance(inp.event, str) else str(inp.event)
        if len(event_text) > 30:
            event_display = event_text[:30] + "..."
        else:
            event_display = event_text
        input_options[str(inp.id)] = f"{event_display}"
    
    selected_input_id = st.selectbox("选择输入数据", list(input_options.keys()), format_func=lambda x: input_options[x], key="edit_input_select")
    
    if not selected_input_id:
        return
    
    selected_input = run_async(get_input(selected_input_id))
    
    if not selected_input:
        return
    
    if f"edit_context_user_{selected_input_id}" not in st.session_state:
        st.session_state[f"edit_context_user_{selected_input_id}"] = ""
        st.session_state[f"edit_context_memory_{selected_input_id}"] = ""
        st.session_state[f"edit_context_vehicle_state_{selected_input_id}"] = ""
        st.session_state[f"edit_context_visual_exterior_{selected_input_id}"] = ""
        st.session_state[f"edit_context_visual_interior_{selected_input_id}"] = ""
        st.session_state[f"edit_context_world_info_{selected_input_id}"] = ""
        
        context_text = selected_input.context if isinstance(selected_input.context, str) else str(selected_input.context)
        if context_text:
            for line in context_text.split("\n"):
                if line.startswith("user: "):
                    st.session_state[f"edit_context_user_{selected_input_id}"] = line[6:]
                elif line.startswith("memory: "):
                    st.session_state[f"edit_context_memory_{selected_input_id}"] = line[8:]
                elif line.startswith("vehicle_state: "):
                    st.session_state[f"edit_context_vehicle_state_{selected_input_id}"] = line[15:]
                elif line.startswith("visual_exterior: "):
                    st.session_state[f"edit_context_visual_exterior_{selected_input_id}"] = line[18:]
                elif line.startswith("visual_interior: "):
                    st.session_state[f"edit_context_visual_interior_{selected_input_id}"] = line[18:]
                elif line.startswith("world_info: "):
                    st.session_state[f"edit_context_world_info_{selected_input_id}"] = line[12:]
    
    with st.expander("🔧 工作环境上下文（可选）"):
        st.markdown("编辑工作环境上下文的各个字段")
        
        user = st.text_area("用户画像（可选）", value=st.session_state[f"edit_context_user_{selected_input_id}"], key=f"edit_context_user_{selected_input_id}")
        memory = st.text_area("记忆（可选）", value=st.session_state[f"edit_context_memory_{selected_input_id}"], key=f"edit_context_memory_{selected_input_id}")
        vehicle_state = st.text_area("车辆状态（可选）", value=st.session_state[f"edit_context_vehicle_state_{selected_input_id}"], key=f"edit_context_vehicle_state_{selected_input_id}")
        visual_exterior = st.text_area("外部视觉信息（可选）", value=st.session_state[f"edit_context_visual_exterior_{selected_input_id}"], key=f"edit_context_visual_exterior_{selected_input_id}")
        visual_interior = st.text_area("内部视觉信息（可选）", value=st.session_state[f"edit_context_visual_interior_{selected_input_id}"], key=f"edit_context_visual_interior_{selected_input_id}")
        world_info = st.text_area("世界信息（可选）", value=st.session_state[f"edit_context_world_info_{selected_input_id}"], key=f"edit_context_world_info_{selected_input_id}")
    
    with st.form(f"edit_input_form_{selected_input_id}"):
        event_text = selected_input.event if isinstance(selected_input.event, str) else str(selected_input.event)
        event = st.text_area("事件 *", value=event_text, key=f"edit_input_event_{selected_input_id}", height=150)
        
        current_dataset_name = "无"
        if selected_input.dataset_id:
            for name, dataset_id in dataset_options.items():
                if dataset_id == str(selected_input.dataset_id):
                    current_dataset_name = name
                    break
        
        dataset_name = st.selectbox("所属数据集（可选）", list(dataset_options.keys()), index=list(dataset_options.keys()).index(current_dataset_name), key=f"edit_input_dataset_{selected_input_id}")
        
        col_update, col_delete = st.columns(2)
        
        with col_update:
            update_submitted = st.form_submit_button("✏️ 更新输入数据", use_container_width=True, key=f"update_input_submit_{selected_input_id}")
        
        with col_delete:
            delete_submitted = st.form_submit_button("🗑️ 删除输入数据", use_container_width=True, key=f"delete_input_submit_{selected_input_id}")
        
        if update_submitted:
            if not event:
                st.error("请填写事件内容")
            else:
                try:
                    context_parts = []
                    if user:
                        context_parts.append(f"user: {user}")
                    if memory:
                        context_parts.append(f"memory: {memory}")
                    if vehicle_state:
                        context_parts.append(f"vehicle_state: {vehicle_state}")
                    if visual_exterior:
                        context_parts.append(f"visual_exterior: {visual_exterior}")
                    if visual_interior:
                        context_parts.append(f"visual_interior: {visual_interior}")
                    if world_info:
                        context_parts.append(f"world_info: {world_info}")
                    
                    context = "\n".join(context_parts) if context_parts else ""
                    
                    dataset_id = dataset_options[dataset_name]
                    input_doc = run_async(update_input(selected_input_id, event, context, dataset_id))
                    st.success(f"✅ 输入数据更新成功！")
                    for key in [f"edit_context_user_{selected_input_id}", f"edit_context_memory_{selected_input_id}", 
                               f"edit_context_vehicle_state_{selected_input_id}", f"edit_context_visual_exterior_{selected_input_id}",
                               f"edit_context_visual_interior_{selected_input_id}", f"edit_context_world_info_{selected_input_id}"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 更新失败: {str(e)}")
        
        if delete_submitted:
            try:
                result = run_async(delete_input(selected_input_id))
                st.success(f"✅ 输入数据删除成功！")
                for key in [f"edit_context_user_{selected_input_id}", f"edit_context_memory_{selected_input_id}", 
                           f"edit_context_vehicle_state_{selected_input_id}", f"edit_context_visual_exterior_{selected_input_id}",
                           f"edit_context_visual_interior_{selected_input_id}", f"edit_context_world_info_{selected_input_id}"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                st.error(f"❌ 删除失败: {str(e)}")


def main() -> None:
    '''
    主函数，整合所有功能
    
    使用 Streamlit 创建一个基于 Tab 的界面，提供数据集和输入数据的完整 CRUD 功能。
    '''
    nest_asyncio.apply()
    
    st.set_page_config(
        page_title="数据集与输入数据管理",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 数据集与输入数据管理")
    st.markdown("---")
    
    get_db_client(
        connection_string="mongodb://localhost:27017",
        database_name="nanoai",
        document_models=[AdvisorDatasetDoc, AdvisorInputDoc]
    )
    
    datasets = run_async(list_datasets())
    inputs = run_async(list_inputs())
    
    tab_dataset, tab_input = st.tabs(["📁 数据集管理", "📝 输入数据管理"])
    
    with tab_dataset:
        st.header("数据集管理")
        st.markdown("---")
        
        subtab_dataset_list, subtab_dataset_create, subtab_dataset_edit = st.tabs(["📋 数据集列表", "➕ 创建数据集", "✏️ 编辑数据集"])
        
        with subtab_dataset_list:
            render_dataset_list(datasets)
        
        with subtab_dataset_create:
            render_create_dataset_form()
        
        with subtab_dataset_edit:
            render_edit_dataset_form(datasets)
    
    with tab_input:
        st.header("输入数据管理")
        st.markdown("---")
        
        subtab_input_list, subtab_input_create, subtab_input_edit = st.tabs(["📋 输入数据列表", "➕ 创建输入数据", "✏️ 编辑输入数据"])
        
        with subtab_input_list:
            render_input_list(inputs, datasets)
        
        with subtab_input_create:
            render_create_input_form(datasets)
        
        with subtab_input_edit:
            render_edit_input_form(inputs, datasets)


if __name__ == "__main__":
    main()
