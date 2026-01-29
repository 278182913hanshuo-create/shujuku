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
        st.info("默认账号: admin / 默认密码: 123456 (可配置)")
        
        with st.form("login_form"):
            username = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")

            if submitted:
                # 优先从 Secrets 读取 [credentials] 配置，如果没有则使用默认值
                # Secrets 格式示例:
                # [credentials]
                # admin = "my_secure_password"
                # user1 = "123456"
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
        # 从 Secrets 读取配置
        if "feishu" not in st.secrets:
            st.error("未找到飞书配置！请在 Secrets 中配置 app_id, app_secret, app_token, table_id。")
            st.stop()
        
        self.app_id = st.secrets["feishu"]["app_id"]
        self.app_secret = st.secrets["feishu"]["app_secret"]
        self.app_token = st.secrets["feishu"]["app_token"]  # 多维表格的 token
        self.table_id = st.secrets["feishu"]["table_id"]    # 数据表的 id
        self.token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        self.base_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"

    def get_token(self):
        """获取 tenant_access_token"""
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
        """获取所有记录"""
        token = self.get_token()
        if not token: return []
        
        headers = {"Authorization": f"Bearer {token}"}
        # 默认查询所有字段
        params = {"page_size": 100} 
        
        try:
            response = requests.get(self.base_url, headers=headers, params=params)
            res_json = response.json()
            
            if res_json.get("code") == 0:
                items = res_json["data"]["items"]
                # 提取 fields 内容，并保留 record_id 用于删除
                clean_data = []
                for item in items:
                    row = item["fields"]
                    row["_record_id"] = item["record_id"] # 隐藏字段，用于删除
                    clean_data.append(row)
                return clean_data
            else:
                st.error(f"读取数据失败: {res_json.get('msg')}")
                return []
        except Exception as e:
            st.error(f"网络请求错误: {e}")
            return []

    def add_record(self, data_dict):
        """添加记录"""
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
        """删除记录"""
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

# 1. 首先检查登录状态
if check_login():

    # 2. 登录成功后，初始化连接器和界面
    connector = FeishuConnector()

    # --- 侧边栏 ---
    st.sidebar.title("🐼 飞书云数据库")
    
    # 添加登出按钮
    if st.sidebar.button("🚪 退出登录"):
        st.session_state.authenticated = False
        st.rerun()
        
    menu = st.sidebar.radio("功能菜单", ["📊 数据查询", "➕ 录入报价", "📈 价格分析"])
    st.sidebar.markdown("---")
    st.sidebar.caption("数据源：飞书多维表格")

    # --- 功能 1: 数据查询 ---
    if menu == "📊 数据查询":
        st.title("📊 供应商设备报价表")
        
        with st.spinner("正在连接飞书服务器..."):
            data = connector.get_records()
        
        if data:
            df = pd.DataFrame(data)
            
            # 调整列顺序（如果有数据）
            # 注意：这里的列名必须与飞书多维表格中的列名完全一致
            cols = ["序号", "项目地点", "设备类型", "设备数量", "单价", "中标合同额", "供货日期", "采购建议", "供应商", "询价单价", "询价总价", "联系人", "录入时间", "备注", "_record_id"]
            
            # 确保列存在，防止飞书字段名不匹配报错
            available_cols = [c for c in cols if c in df.columns]
            df = df[available_cols]

            # 搜索框
            col1, col2 = st.columns(2)
            with col1:
                search_supplier = st.text_input("🔍 搜索供应商")
            with col2:
                search_equipment = st.text_input("🔍 搜索设备类型")
            
            if search_supplier:
                df = df[df['供应商'].astype(str).str.contains(search_supplier, case=False)]
            if search_equipment:
                # 兼容旧数据，如果'设备类型'列不存在则不报错
                if '设备类型' in df.columns:
                    df = df[df['设备类型'].astype(str).str.contains(search_equipment, case=False)]
                
            # 展示表格 (隐藏 record_id)
            display_df = df.drop(columns=["_record_id"], errors='ignore')
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # 删除功能
            with st.expander("🗑️ 管理数据"):
                if "_record_id" in df.columns:
                    # 制作下拉选项：显示名称，但对应 ID
                    record_options = df.to_dict('records')
                    # 格式化显示函数
                    def format_func(option):
                        supplier = option.get('供应商', '未命名')
                        device = option.get('设备类型', '未知设备')
                        price = option.get('单价', 0)
                        return f"{supplier} - {device} (￥{price})"
                    
                    selected_record = st.selectbox("选择要删除的记录", options=record_options, format_func=format_func)
                    
                    if st.button("确认删除"):
                        if connector.delete_record(selected_record["_record_id"]):
                            st.success("删除成功！")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.warning("无法获取记录ID，无法执行删除操作。")

        else:
            st.info("表格为空，或连接飞书失败。请先录入数据。")

    # --- 功能 2: 录入报价 ---
    elif menu == "➕ 录入报价":
        st.title("➕ 录入新报价")
        
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
                # 必填项检查 (根据实际情况调整)
                if supplier and device_type:
                    payload = {
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
                        st.success(f"已同步至飞书：{supplier} - {device_type}")
                else:
                    st.warning("请至少填写 '供应商' 和 '设备类型'")

    # --- 功能 3: 价格分析 ---
    elif menu == "📈 价格分析":
        st.title("📈 数据分析")
        data = connector.get_records()
        if data:
            df = pd.DataFrame(data)
            # 简单的图表分析
            if "单价" in df.columns and "设备类型" in df.columns:
                st.subheader("设备类型 vs 中标单价")
                # 确保数据是数值型
                df['单价'] = pd.to_numeric(df['单价'], errors='coerce')
                st.bar_chart(df, x="设备类型", y="单价")
            elif "询价单价" in df.columns and "设备类型" in df.columns:
                st.subheader("设备类型 vs 询价单价")
                df['询价单价'] = pd.to_numeric(df['询价单价'], errors='coerce')
                st.bar_chart(df, x="设备类型", y="询价单价")
            else:
                st.info("数据字段不足，无法生成图表。请确保飞书表头包含 '设备类型' 和 '单价'。")
