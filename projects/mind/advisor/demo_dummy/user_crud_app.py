'''UserDoc CRUD 应用 - Streamlit 前端（使用 Beanie ODM）

这是一个基于 Streamlit 的用户管理系统，用于演示如何使用 Beanie ODM 进行 MongoDB 的 CRUD 操作。

Streamlit 是一个用于快速构建数据应用的 Python 框架，它提供了丰富的 UI 组件和交互功能。
'''

import nest_asyncio
import streamlit as st
from typing import Any

from projects.mind.advisor.mdb_models.user import UserDoc
from projects.mind.advisor.domain_data.user import Preference, UserBase
from projects.mind.advisor.demo_dummy.streamlit_utils import get_db_client, run_async


async def get_all_users() -> list[UserDoc]:
    ''' 
    获取所有用户
    
    使用 Beanie 的 find() 方法查询所有用户文档，
    to_list() 将查询结果转换为列表。
    
    返回:
        list[UserDoc]: 用户文档列表
    '''
    return await UserDoc.find().to_list()


async def create_user(
    name: str, 
    age: int, 
    gender: str | None = None, 
    preferences: list[Preference] | None = None,
    attributes: dict[str, str] | None = None
    ) -> UserDoc:
    '''
    创建新用户
    
    参数:
        name: 用户姓名
        age: 用户年龄
        gender: 用户性别（可选）
        preferences: 用户偏好列表（可选）
        attributes: 用户属性字典（可选）
        
    返回:
        UserDoc: 创建的用户文档对象
    '''
    user = UserDoc(name=name, age=age, gender=gender, preferences=preferences, attributes=attributes)
    await user.insert()
    return user


async def update_user(
    user_id: str, 
    name: str, 
    age: int, 
    gender: str | None = None, 
    preferences: list[Preference] | None = None,
    attributes: dict[str, str] | None = None
    ) -> UserDoc | None:
    '''
    更新用户信息
    
    参数:
        user_id: 用户 ID
        name: 新的姓名
        age: 新的年龄
        gender: 新的性别（可选）
        preferences: 新的用户偏好列表（可选）
        attributes: 新的用户属性字典（可选）
        
    返回:
        Optional[UserDoc]: 更新后的用户文档，如果用户不存在则返回 None
    '''
    user = await UserDoc.get(user_id)
    if user:
        user.name = name
        user.age = age
        user.gender = gender
        user.preferences = preferences
        user.attributes = attributes
        await user.save()
        return user
    return None


async def delete_user(user_id: str) -> int:
    '''
    删除用户
    
    参数:
        user_id: 用户 ID
        
    返回:
        int: 删除的文档数量
    '''
    return await UserDoc.delete(user_id)


async def get_user(user_id: str) -> UserDoc | None:
    '''
    获取单个用户
    
    参数:
        user_id: 用户 ID
        
    返回:
        Optional[UserDoc]: 用户文档对象，如果不存在则返回 None
    '''
    return await UserDoc.get(user_id)


def render_create_user_form() -> None:
    '''
    渲染创建用户表单
    
    提供姓名、年龄、性别输入字段，提交后创建新用户。
    使用 expander 提供偏好和属性编辑功能。
    '''
    if "create_prefs" not in st.session_state:
        st.session_state.create_prefs = []
    
    if "create_attrs" not in st.session_state:
        st.session_state.create_attrs = {}
    
    with st.expander("📋 用户偏好（可选）"):
        st.markdown("添加用户的偏好描述")
        
        add_pref = st.text_input("新偏好描述", key="create_new_pref")
        add_button = st.button("➕ 添加偏好", key="create_add_pref")
        
        if add_button and add_pref:
            st.session_state.create_prefs.append(add_pref)
            st.rerun()
        
        if st.session_state.create_prefs:
            st.markdown("**当前偏好列表：**")
            for i, pref in enumerate(st.session_state.create_prefs):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.text(f"{i + 1}. {pref}")
                with col2:
                    if st.button("🗑️", key=f"create_del_pref_{i}"):
                        st.session_state.create_prefs.pop(i)
                        st.rerun()
        else:
            st.info("暂无偏好")
    
    with st.expander("🔧 用户属性（可选）"):
        st.markdown("添加用户的键值对属性")
        
        col1, col2, col3 = st.columns([3, 3, 1])
        with col1:
            new_attr_key = st.text_input("属性键", key="create_new_attr_key")
        with col2:
            new_attr_value = st.text_input("属性值", key="create_new_attr_value")
        with col3:
            add_attr_button = st.button("➕", key="create_add_attr")
        
        if add_attr_button and new_attr_key and new_attr_value:
            st.session_state.create_attrs[new_attr_key] = new_attr_value
            st.rerun()
        
        if st.session_state.create_attrs:
            st.markdown("**当前属性列表：**")
            for key, value in st.session_state.create_attrs.items():
                col1, col2, col3 = st.columns([3, 3, 1])
                with col1:
                    st.text(key)
                with col2:
                    st.text(value)
                with col3:
                    if st.button("🗑️", key=f"create_del_attr_{key}"):
                        del st.session_state.create_attrs[key]
                        st.rerun()
        else:
            st.info("暂无属性")
    
    with st.form("create_user_form"):
        name = st.text_input("姓名 *", key="create_name")
        age = st.number_input("年龄 *", min_value=0, max_value=150, value=0, key="create_age")
        gender = st.selectbox("性别", ["男", "女", "其他", None], index=3, key="create_gender")
        
        submitted = st.form_submit_button("✅ 创建用户", use_container_width=True)
        
        if submitted:
            if not name or age == 0:
                st.error("请填写姓名和年龄")
            else:
                try:
                    preferences = [Preference(desc=pref) for pref in st.session_state.create_prefs] if st.session_state.create_prefs else None
                    attributes = st.session_state.create_attrs if st.session_state.create_attrs else None
                    user = run_async(create_user(name, age, gender if gender != "其他" else None, preferences, attributes))
                    st.success(f"✅ 用户创建成功！ID: {user.id}")
                    st.session_state.create_prefs = []
                    st.session_state.create_attrs = {}
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 创建失败: {str(e)}")


def render_edit_user_form(users: list[UserDoc]) -> None:
    '''
    渲染编辑用户表单
    
    参数:
        users: 用户列表，用于生成选择下拉框
        
    提供用户选择、姓名、年龄、性别编辑字段，支持更新和删除操作。
    使用 expander 提供偏好和属性编辑功能。
    '''
    if not users:
        st.info("暂无用户数据，请先创建用户")
        return
    
    user_options = {str(u.id): f"{u.name} ({u.age}岁)" for u in users}
    selected_user_id = st.selectbox("选择用户", list(user_options.keys()), format_func=lambda x: user_options[x], key="edit_user_select")
    
    if not selected_user_id:
        return
    
    selected_user = run_async(get_user(selected_user_id))
    
    if not selected_user:
        return
    
    if f"edit_prefs_{selected_user_id}" not in st.session_state:
        st.session_state[f"edit_prefs_{selected_user_id}"] = [pref.desc for pref in selected_user.preferences] if selected_user.preferences else []
    
    if f"edit_attrs_{selected_user_id}" not in st.session_state:
        st.session_state[f"edit_attrs_{selected_user_id}"] = selected_user.attributes if selected_user.attributes else {}
    
    with st.expander("📋 用户偏好（可选）"):
        st.markdown("编辑用户的偏好描述")
        
        add_pref = st.text_input("新偏好描述", key=f"edit_new_pref_{selected_user_id}")
        add_button = st.button("➕ 添加偏好", key=f"edit_add_pref_{selected_user_id}")
        
        if add_button and add_pref:
            st.session_state[f"edit_prefs_{selected_user_id}"].append(add_pref)
            st.rerun()
        
        if st.session_state[f"edit_prefs_{selected_user_id}"]:
            st.markdown("**当前偏好列表：**")
            for i, pref in enumerate(st.session_state[f"edit_prefs_{selected_user_id}"]):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.text(f"{i + 1}. {pref}")
                with col2:
                    if st.button("🗑️", key=f"edit_del_pref_{selected_user_id}_{i}"):
                        st.session_state[f"edit_prefs_{selected_user_id}"].pop(i)
                        st.rerun()
        else:
            st.info("暂无偏好")
    
    with st.expander("🔧 用户属性（可选）"):
        st.markdown("编辑用户的键值对属性")
        
        col1, col2, col3 = st.columns([3, 3, 1])
        with col1:
            new_attr_key = st.text_input("属性键", key=f"edit_new_attr_key_{selected_user_id}")
        with col2:
            new_attr_value = st.text_input("属性值", key=f"edit_new_attr_value_{selected_user_id}")
        with col3:
            add_attr_button = st.button("➕", key=f"edit_add_attr_{selected_user_id}")
        
        if add_attr_button and new_attr_key and new_attr_value:
            st.session_state[f"edit_attrs_{selected_user_id}"][new_attr_key] = new_attr_value
            st.rerun()
        
        if st.session_state[f"edit_attrs_{selected_user_id}"]:
            st.markdown("**当前属性列表：**")
            for key, value in st.session_state[f"edit_attrs_{selected_user_id}"].items():
                col1, col2, col3 = st.columns([3, 3, 1])
                with col1:
                    st.text(key)
                with col2:
                    st.text(value)
                with col3:
                    if st.button("🗑️", key=f"edit_del_attr_{selected_user_id}_{key}"):
                        del st.session_state[f"edit_attrs_{selected_user_id}"][key]
                        st.rerun()
        else:
            st.info("暂无属性")
    
    with st.form(f"edit_user_form_{selected_user_id}"):
        name = st.text_input("姓名 *", value=selected_user.name, key=f"edit_name_{selected_user_id}")
        age = st.number_input("年龄 *", min_value=0, max_value=150, value=selected_user.age, key=f"edit_age_{selected_user_id}") # type: ignore
        gender_options = ["男", "女", "其他", None]
        gender_index = 0
        if selected_user.gender == "女":
            gender_index = 1
        elif selected_user.gender == "其他":
            gender_index = 2
        elif selected_user.gender is None:
            gender_index = 3
        gender = st.selectbox("性别", gender_options, index=gender_index, key=f"edit_gender_{selected_user_id}")
        
        col_update, col_delete = st.columns(2)
        
        with col_update:
            update_submitted = st.form_submit_button("✏️ 更新用户", use_container_width=True)
        
        with col_delete:
            delete_submitted = st.form_submit_button("🗑️ 删除用户", use_container_width=True)
        
        if update_submitted:
            if not name or age == 0:
                st.error("请填写姓名和年龄")
            else:
                try:
                    preferences = [Preference(desc=pref) for pref in st.session_state[f"edit_prefs_{selected_user_id}"]] if st.session_state[f"edit_prefs_{selected_user_id}"] else None
                    attributes = st.session_state[f"edit_attrs_{selected_user_id}"] if st.session_state[f"edit_attrs_{selected_user_id}"] else None
                    user = run_async(update_user(
                        selected_user_id,
                        name,
                        age,
                        gender if gender != "其他" else None,
                        preferences,
                        attributes
                    ))
                    st.success(f"✅ 用户更新成功！")
                    del st.session_state[f"edit_prefs_{selected_user_id}"]
                    del st.session_state[f"edit_attrs_{selected_user_id}"]
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 更新失败: {str(e)}")
        
        if delete_submitted:
            try:
                result = run_async(delete_user(selected_user_id))
                st.success(f"✅ 用户删除成功！")
                if f"edit_prefs_{selected_user_id}" in st.session_state:
                    del st.session_state[f"edit_prefs_{selected_user_id}"]
                if f"edit_attrs_{selected_user_id}" in st.session_state:
                    del st.session_state[f"edit_attrs_{selected_user_id}"]
                st.rerun()
            except Exception as e:
                st.error(f"❌ 删除失败: {str(e)}")


def render_user_list(users: list[UserDoc]) -> None:
    '''
    渲染用户列表
    
    显示所有用户的详细信息，包括姓名、年龄、性别、偏好、属性、创建时间、更新时间。
    提供刷新按钮和用户总数统计。
    '''
    if st.button("🔄 刷新列表", use_container_width=True):
        st.rerun()

    if not users:
        st.info("暂无用户数据")
        return

    user_data: list[dict[str, Any]] = []
    for user in users:
        if user.preferences and len(user.preferences) > 0:
            pref_descs = [pref.desc for pref in user.preferences]
            if len(pref_descs) <= 2:
                prefs_display = ", ".join(pref_descs)
            else:
                prefs_display = f"{', '.join(pref_descs[:2])} 等 {len(pref_descs)} 项"
        else:
            prefs_display = "-"
        
        if user.attributes and len(user.attributes) > 0:
            attr_items = list(user.attributes.items())
            if len(attr_items) <= 2:
                attrs_display = ", ".join([f"{k}: {v}" for k, v in attr_items])
            else:
                attrs_display = f"{', '.join([f'{k}: {v}' for k, v in attr_items[:2]])} 等 {len(attr_items)} 项"
        else:
            attrs_display = "-"
        
        user_data.append({
            "姓名": user.name or "-",
            "年龄": user.age or "-",
            "性别": user.gender or "-",
            "偏好": prefs_display,
            "属性": attrs_display,
            "创建时间": user.created_time.strftime("%Y-%m-%d %H:%M:%S") if user.created_time else "-",
            "更新时间": user.updated_time.strftime("%Y-%m-%d %H:%M:%S") if user.updated_time else "-"
        })

    st.dataframe(
        user_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ID": st.column_config.TextColumn("ID", width="small"),
            "姓名": st.column_config.TextColumn("姓名", width="medium"),
            "年龄": st.column_config.NumberColumn("年龄", width="small"),
            "性别": st.column_config.TextColumn("性别", width="small"),
            "偏好": st.column_config.TextColumn("偏好", width="medium"),
            "属性": st.column_config.TextColumn("属性", width="medium"),
            "创建时间": st.column_config.DatetimeColumn("创建时间", width="medium"),
            "更新时间": st.column_config.DatetimeColumn("更新时间", width="medium")
        }
    )

    st.markdown("---")
    st.metric("用户总数", len(users))


def main() -> None:
    '''
    主函数 - Streamlit 应用的入口
    
    这个函数构建整个用户管理界面，包括：
    1. 应用启动配置（nest_asyncio）
    2. 页面配置
    3. 初始化数据库连接
    4. 创建两列布局
    5. 左侧：创建/编辑用户表单
    6. 右侧：用户列表展示
    '''
    nest_asyncio.apply()
    
    st.set_page_config(
        page_title="用户管理",
        page_icon="👤",
        layout="wide"
    )

    st.title("👤 用户管理系统")
    st.markdown("---")

    get_db_client(
        connection_string="mongodb://localhost:27017",
        database_name="mydb",
        document_models=[UserDoc]
    )

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("📝 创建/编辑用户")

        mode = st.radio(
            "操作模式",
            ["创建用户", "编辑用户"],
            horizontal=True
        )

        if mode == "创建用户":
            render_create_user_form()
        else:
            users = run_async(get_all_users())
            render_edit_user_form(users)

    with col2:
        st.subheader("📋 用户列表")
        users = run_async(get_all_users())
        render_user_list(users)


if __name__ == "__main__":
    main()
