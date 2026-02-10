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
        st.info("")
        
        with st.form("login_form"):
            username = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")

            if submitted:
                # 优先从 Secrets 读取 [credentials] 配置
                valid_users = st.secrets.get("credentials", {"admin": "123456"})
                
                if username in valid_users and valid_users[username] == password:
                    st.session_state.authenticated = True
                    st.success("登录成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("账号或密码错误，请重试。")
    
    return False

# --- 飞书 API 工具类 ---
class FeishuConnector:
    def __init__(self):
        if "feishu" not in st.secrets:
            st.error("未找到飞书配置！请在 Secrets 中配置 app_id, app_secret, app_token, table_id。")
            st.stop()
        
        self.app_id = st.secrets["feishu"]["app_id"]
        self.app_secret = st.secrets["feishu"]["app_secret"]
        self.app_token = st.secrets["feishu"]["app_token"]
        self.table_id = st.secrets["feishu"]["table_id"]
        self.token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        self.base_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"

    def get_token(self):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        response = requests.post(self.token_url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json().get("tenant_access_token")
        else:
            st.error(f"获取 Token 失败: {response.text}")
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
            st.error(f"网络请求错误: {e}")
            return []

    def add_record(self, data_dict):
        token = self.get_token()
        if not token: return False
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {"fields": data_dict}
        
        response = requests.post(self.base_url, headers=headers, json=payload)
        res_json = response.json()
        
        if res_json.get("code") == 0:
            return True
        else:
            st.error(f"写入失败: {res_json.get('msg')}")
            return False

    def delete_record(self, record_id):
        token = self.get_token()
        if not token: return False
        
        headers = {"Authorization": f"Bearer {token}"}
        delete_url = f"{self.base_url}/{record_id}"
        
        response = requests.delete(delete_url, headers=headers)
        res_json = response.json()
        
        if res_json.get("code") == 0:
            return True
        else:
            st.error(f"删除失败: {res_json.get('msg')}")
            return False

# ==========================================
#  主程序逻辑
# ==========================================

if check_login():
    connector = FeishuConnector()

    st.sidebar.title("🐼 飞书云数据库")
    
    if st.sidebar.button("🚪 退出登录"):
        st.session_state.authenticated = False
        st.rerun()
        
    menu = st.sidebar.radio("功能菜单", ["📊 数据查询", "➕ 录入报价", "📈 价格分析"])
    st.sidebar.markdown("---")
    st.sidebar.caption("数据源：飞书多维表格")

    # 定义部门列表
    DEPARTMENTS = ["电力物联网中心", "数字化中心", "信通和镇江分公司"]

    # --- 功能 1: 数据查询 ---
    if menu == "📊 数据查询":
        st.title("📊 供应商采购成本数据库")
        
        with st.spinner("正在连接飞书服务器..."):
            data = connector.get_records()
        
        if data:
            df = pd.DataFrame(data)
            
            # 这里的列名必须与飞书多维表格中的列名完全一致
            cols = ["序号", "所属部门", "项目地点", "设备类型", "设备数量", "单价", "中标合同额", "供货日期", "采购建议", "供应商", "询价单价", "询价总价", "联系人", "录入时间", "备注", "_record_id"]
            
            # 确保列存在
            available_cols = [c for c in cols if c in df.columns]
            df = df[available_cols]

            # 使用 Tabs 划分三个部门
            tabs = st.tabs(DEPARTMENTS)
            
            for i, dept_name in enumerate(DEPARTMENTS):
                with tabs[i]:
                    st.header(f"📁 {dept_name} 数据")
                    
                    # 筛选对应部门的数据
                    if "所属部门" in df.columns:
                        dept_df = df[df["所属部门"] == dept_name]
                    else:
                        dept_df = pd.DataFrame(columns=available_cols)
                        if i == 0: st.warning("⚠️ 警告：检测到飞书表格缺少【所属部门】列，无法进行分类筛选。请去飞书添加该列。")

                    # 部门内的搜索
                    c1, c2 = st.columns(2)
                    with c1:
                        # 加上key避免组件ID冲突
                        search_supplier = st.text_input(f"🔍 搜索供应商 ({dept_name})", key=f"search_s_{i}")
                    with c2:
                        search_equipment = st.text_input(f"🔍 搜索设备类型 ({dept_name})", key=f"search_e_{i}")
                    
                    if search_supplier:
                        dept_df = dept_df[dept_df['供应商'].astype(str).str.contains(search_supplier, case=False)]
                    if search_equipment and '设备类型' in dept_df.columns:
                        dept_df = dept_df[dept_df['设备类型'].astype(str).str.contains(search_equipment, case=False)]
                    
                    # 展示表格
                    display_df = dept_df.drop(columns=["_record_id"], errors='ignore')
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                    # 删除功能
                    with st.expander(f"🗑️ 管理 {dept_name} 数据"):
                        if not dept_df.empty and "_record_id" in dept_df.columns:
                            record_options = dept_df.to_dict('records')
                            def format_func(option):
                                supplier = option.get('供应商', '未命名')
                                device = option.get('设备类型', '未知设备')
                                price = option.get('单价', 0)
                                return f"{supplier} - {device} (￥{price})"
                            
                            selected_record = st.selectbox("选择要删除的记录", options=record_options, format_func=format_func, key=f"del_sel_{i}")
                            
                            if st.button("确认删除", key=f"del_btn_{i}"):
                                if connector.delete_record(selected_record["_record_id"]):
                                    st.success("删除成功！")
                                    time.sleep(1)
                                    st.rerun()
                        else:
                            st.info("当前分类下暂无数据可管理")

        else:
            st.info("表格为空，或连接飞书失败。请先录入数据。")

    # --- 功能 2: 录入报价 ---
    elif menu == "➕ 录入报价":
        st.title("➕ 录入新报价")
        
        # 部门选择器（放在表单外，明确分类）
        st.subheader("1. 选择所属部门")
        selected_dept = st.selectbox("请选择数据归属部门", DEPARTMENTS)
        
        st.subheader("2. 填写详细信息")
        with st.form("feishu_entry"):
            # 第一行
            c1, c2, c3 = st.columns(3)
            with c1:
                seq_num = st.text_input("序号")
                project_loc = st.text_input("项目地点")
                device_type = st.text_input("设备类型")
            with c2:
                supplier = st.text_input("供应商")
                contact = st.text_input("联系人")
                supply_date = st.text_input("供货日期 (选填)")
            with c3:
                device_count = st.number_input("设备数量", min_value=0, step=1)
                purchase_advice = st.text_input("采购建议")
            
            st.markdown("---")
            # 第二行：价格相关
            c4, c5, c6, c7 = st.columns(4)
            with c4:
                unit_price = st.number_input("单价 (中标)", min_value=0.0)
            with c5:
                contract_amt = st.number_input("中标合同额", min_value=0.0)
            with c6:
                inquiry_unit = st.number_input("询价单价", min_value=0.0)
            with c7:
                inquiry_total = st.number_input("询价总价", min_value=0.0)
            
            note = st.text_area("备注")
            submitted = st.form_submit_button("🚀 提交到飞书")
            
            if submitted:
                # 必填项检查
                if supplier and device_type:
                    payload = {
                        "所属部门": selected_dept,  # 写入选择的部门
                        "序号": seq_num,
                        "项目地点": project_loc,
                        "设备类型": device_type,
                        "设备数量": device_count,
                        "单价": unit_price,
                        "中标合同额": contract_amt,
                        "供货日期": supply_date,
                        "采购建议": purchase_advice,
                        "供应商": supplier,
                        "询价单价": inquiry_unit,
                        "询价总价": inquiry_total,
                        "联系人": contact,
                        "备注": note,
                        "录入时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    if connector.add_record(payload):
                        st.success(f"已同步至飞书 [{selected_dept}]：{supplier} - {device_type}")
                else:
                    st.warning("请至少填写 '供应商' 和 '设备类型'")

    # --- 功能 3: 价格分析 ---
    elif menu == "📈 价格分析":
        st.title("📈 数据分析")
        data = connector.get_records()
        if data:
            df = pd.DataFrame(data)
            
            # 增加部门筛选器
            st.subheader("部门分析筛选")
            dept_filter = st.multiselect("选择要分析的部门", DEPARTMENTS, default=DEPARTMENTS)
            
            if "所属部门" in df.columns:
                df = df[df["所属部门"].isin(dept_filter)]
            
            # 图表
            if not df.empty:
                if "单价" in df.columns and "设备类型" in df.columns:
                    st.subheader("设备类型 vs 中标单价")
                    df['单价'] = pd.to_numeric(df['单价'], errors='coerce')
                    st.bar_chart(df, x="设备类型", y="单价")
                else:
                    st.info("数据字段不足，无法生成图表。")
            else:
                st.info("所选部门暂无数据。")

