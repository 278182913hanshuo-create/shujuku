import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import time

# --- 页面配置 ---
st.set_page_config(
    page_title="供应商设备价格数据库 (飞书版)",
    page_icon="🐼",
    layout="wide"
)

# --- 登录验证功能 ---
def check_login():
    """简单的登录验证"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 系统登录")
        with st.form("login_form"):
            username = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")

            if submitted:
                valid_users = st.secrets.get("credentials", {"admin": "123456"})
                if username in valid_users and valid_users[username] == password:
                    st.session_state.authenticated = True
                    st.success("登录成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("账号或密码错误。")
    return False

# --- 飞书 API 工具类 ---
class FeishuConnector:
    def __init__(self):
        if "feishu" not in st.secrets:
            st.error("未找到飞书配置！请在 Secrets 中配置。")
            st.stop()
        
        self.app_id = st.secrets["feishu"]["app_id"]
        self.app_secret = st.secrets["feishu"]["app_secret"]
        self.app_token = st.secrets["feishu"]["app_token"]
        self.table_id = st.secrets["feishu"]["table_id"]
        self.token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        self.base_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"

    def get_token(self):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        data = {"app_id": self.app_id, "app_secret": self.app_secret}
        try:
            response = requests.post(self.token_url, headers=headers, json=data)
            return response.json().get("tenant_access_token")
        except:
            return None

    def get_records(self):
        token = self.get_token()
        if not token: return []
        
        headers = {"Authorization": f"Bearer {token}"}
        params = {"page_size": 100} 
        
        try:
            response = requests.get(self.base_url, headers=headers, params=params)
            res_json = response.json()
            if res_json.get("code") == 0:
                items = res_json["data"]["items"]
                clean_data = []
                for item in items:
                    row = item["fields"]
                    row["_record_id"] = item["record_id"]
                    clean_data.append(row)
                return clean_data
            else:
                st.error(f"读取数据失败: {res_json.get('msg')}")
                return []
        except Exception as e:
            st.error(f"请求错误: {e}")
            return []

    def add_record(self, data_dict):
        token = self.get_token()
        if not token: return False
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {"fields": data_dict}
        response = requests.post(self.base_url, headers=headers, json=payload)
        return response.json().get("code") == 0

    def delete_record(self, record_id):
        token = self.get_token()
        if not token: return False
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.delete(f"{self.base_url}/{record_id}", headers=headers)
        return response.json().get("code") == 0

# ==========================================
#  主程序逻辑
# ==========================================

if check_login():
    connector = FeishuConnector()

    st.sidebar.title("🐼 飞书云数据库")
    
    # --- 调试工具 ---
    with st.sidebar.expander("🔧 调试模式 (列名检查)"):
        st.write("如果你发现数据没显示，可能是飞书里的列名和代码不一致。")
        show_debug = st.checkbox("显示原始列名")

    if st.sidebar.button("🚪 退出登录"):
        st.session_state.authenticated = False
        st.rerun()
        
    menu = st.sidebar.radio("功能菜单", ["📊 数据查询", "➕ 录入报价", "📈 价格分析"])

    # --- 功能 1: 数据查询 ---
    if menu == "📊 数据查询":
        st.title("📊 供应商采购成本数据库")
        
        with st.spinner("正在连接飞书服务器..."):
            data = connector.get_records()
        
        if data:
            df = pd.DataFrame(data)
            
            # --- 调试显示 ---
            if show_debug:
                st.info(f"飞书返回的实际列名: {list(df.columns)}")
                st.write("请确保飞书里的列名与下方录入代码中的字段一致。")

            # 检查关键列是否存在
            has_dept = "所属部门" in df.columns
            
            if not has_dept:
                st.warning("⚠️ 未检测到【所属部门】列。暂时显示全部数据，请去飞书添加该列以启用分类功能。")
                # 如果没有部门列，直接显示整个表格
                st.dataframe(df.drop(columns=["_record_id"], errors="ignore"), use_container_width=True)
                
            else:
                # 如果有部门列，使用 Tabs 分类
                depts = list(df["所属部门"].dropna().unique())
                if not depts:
                    depts = ["暂无部门数据"]
                
                tabs = st.tabs(depts)
                
                for i, dept_name in enumerate(depts):
                    with tabs[i]:
                        # 筛选数据
                        dept_df = df[df["所属部门"] == dept_name]
                        
                        # 搜索功能
                        col1, col2 = st.columns(2)
                        with col1:
                            search_q = st.text_input(f"🔍 搜索 ({dept_name})", key=f"s_{i}")
                        
                        if search_q:
                            # 模糊搜索所有列
                            mask = dept_df.astype(str).apply(lambda x: x.str.contains(search_q, case=False)).any(axis=1)
                            dept_df = dept_df[mask]

                        # 显示表格 (自动显示所有列，不再硬编码过滤)
                        st.dataframe(
                            dept_df.drop(columns=["_record_id"], errors="ignore"), 
                            use_container_width=True,
                            hide_index=True
                        )

                        # 删除功能
                        with st.expander(f"🗑️ 删除 {dept_name} 的记录"):
                            if not dept_df.empty:
                                options = dept_df.to_dict('records')
                                # 尝试智能生成显示名称
                                def fmt(opt):
                                    # 尝试找一些常见的名字作为标签
                                    name = opt.get("设备类型") or opt.get("设备名称") or opt.get("项目地点") or "未知项"
                                    price = opt.get("单价") or opt.get("中标合同额") or "0"
                                    return f"{name} (￥{price})"
                                
                                sel = st.selectbox("选择记录", options, format_func=fmt, key=f"d_{i}")
                                if st.button("确认删除", key=f"btn_{i}"):
                                    if connector.delete_record(sel["_record_id"]):
                                        st.success("删除成功")
                                        time.sleep(1)
                                        st.rerun()
        else:
            st.info("表格为空，或连接失败。")

    # --- 功能 2: 录入报价 ---
    elif menu == "➕ 录入报价":
        st.title("➕ 录入新报价")
        st.caption("注意：此处修改仅影响新录入的数据，不会自动修改旧数据的列名。")
        
        with st.form("new_entry"):
            c1, c2 = st.columns(2)
            with c1:
                # 这里的 label 就是写入飞书的 key
                # 如果飞书里叫 "设备名称"，这里就得改叫 "设备名称"
                dept = st.text_input("所属部门", placeholder="例如：电力物联网中心")
                project = st.text_input("项目地点")
                device = st.text_input("设备类型") 
            with c2:
                supplier = st.text_input("供应商")
                price = st.number_input("单价", min_value=0.0)
                count = st.number_input("设备数量", min_value=0, step=1)
            
            # 更多可选字段
            with st.expander("更多详细信息"):
                contract_amt = st.number_input("中标合同额", min_value=0.0)
                date = st.text_input("供货日期")
                contact = st.text_input("联系人")
                note = st.text_area("备注")

            submitted = st.form_submit_button("🚀 提交")

            if submitted:
                # 构建数据字典
                payload = {
                    "所属部门": dept,
                    "项目地点": project,
                    "设备类型": device,
                    "供应商": supplier,
                    "单价": price,
                    "设备数量": count,
                    "中标合同额": contract_amt,
                    "供货日期": date,
                    "联系人": contact,
                    "备注": note,
                    "录入时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # 清除空值，防止写入错误
                clean_payload = {k: v for k, v in payload.items() if v}
                
                if connector.add_record(clean_payload):
                    st.success("✅ 写入成功！如果表格里没显示，请检查飞书列名是否与上方输入框标题一致。")

    # --- 功能 3: 价格分析 ---
    elif menu == "📈 价格分析":
        st.title("📈 简易分析")
        data = connector.get_records()
        if data:
            df = pd.DataFrame(data)
            if not df.empty:
                # 尝试智能识别数值列
                num_cols = df.select_dtypes(include=['float', 'int']).columns.tolist()
                # 尝试识别文本列
                text_cols = df.select_dtypes(include=['object']).columns.tolist()
                
                if num_cols and text_cols:
                    x_axis = st.selectbox("选择X轴 (分类)", text_cols, index=0)
                    y_axis = st.selectbox("选择Y轴 (数值)", num_cols, index=0)
                    st.bar_chart(df, x=x_axis, y=y_axis)
                else:
                    st.write("数据格式不足以生成图表 (需要至少一列数字和一列文本)")
            else:
                st.info("暂无数据")
