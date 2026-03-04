import os
from openai import OpenAI

# 请确保您已将 API Key 存储在环境变量 ARK_API_KEY 中
# 初始化Openai客户端，从环境变量中读取您的API Key
client = OpenAI(
    # 此为默认路径，您可根据业务所在地域进行配置
    base_url="https://ark.cn-beijing.volces.com/api/v3/bots",
    # 从环境变量中获取您的 API Key
    # api_key=os.environ.get("314e7fef-5bc4-42eb-b523-ba1fe9936749")
    api_key="314e7fef-5bc4-42eb-b523-ba1fe9936749"
)


# Non-streaming:
# print("----- standard request -----")
completion = client.chat.completions.create(
    model="bot-20250828104012-tt5dl",  # bot-20250828104012-tt5dl 为您当前的智能体的ID，注意此处与Chat API存在差异。差异对比详见 SDK使用指南
    messages=[
        {"role": "system", "content": "你是豆包，是由字节跳动开发的 AI 人工智能助手"},
        {"role": "user", "content": 
         
         """
# 角色：电子元器件专家

# bom【bom】: 
```
[
  {
    "元件ID": "U1",
    "型号": "MAX77860EWG+T",
    "零件名称": "电池管理",
    "规格描述": "USB Type-C、3A、开关模式Buck充电器，具有集成CC检测、反向升压和ADC",
    "单机用量": 1,
    "默认供应商": "亚德诺",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/items/07c9ddbd9/b8e104f564f0a24b8d82afcc10d9d84cd840d703.pdf",
    "价格": 38.26,
    "替代料": []
  },
  {
    "元件ID": "U2",
    "型号": "MIC2205-1.8YMLTR",
    "零件名称": "DC-DC稳压器",
    "规格描述": "2A SWITCHING REGULATOR, 2200kHz SWITCHING FREQ-MAX, PDSO10, 3 X 3 MM, LEAD FREE, MLF-10",
    "单机用量": 1,
    "默认供应商": "美国微芯",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/network_download/2022/10/10/1579424645935058946.pdf",
    "价格": "",
    "替代料": []
  },
  {
    "元件ID": "U3",
    "型号": "HC32F052FATB-LQ32",
    "零件名称": "MCU",
    "规格描述": "型号: HC32F052FATB-LQ32; 描述: 32位ARM® Cortex®-M0+微控制器（具体ADC通道数和存储容量需查规格书）",
    "单机用量": 1,
    "默认供应商": "小华半导体",
    "用户指定": true,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/items/5d260e2d6/475a9c9ea16953be69de7d38abaaaa6507b9baf6.pdf",
    "价格": "",
    "替代料": []
  },
  {
    "元件ID": "U4",
    "型号": "AD7988-5BRMZ",
    "零件名称": "数据转换ADC/DAC",
    "规格描述": "16位、500ksps、超低功耗16位SAR ADC",
    "单机用量": 1,
    "默认供应商": "亚德诺",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/items/07c9ddbd9/e8c2d0f92811017bb725394f909ca5b477a2a73c.pdf",
    "价格": 106.01,
    "替代料": []
  },
  {
    "元件ID": "U5",
    "型号": "LM393",
    "零件名称": "比较器",
    "规格描述": "'最高工作温度': '+70℃', '丝印': '393', 'ICCTyp (mA)': '0.4,0.7', 'Channels': '2', 'TAMin (°C)': '0', 'tresTyp (ns)': '1300', 'TAMax (°C)': '70', 'VCCMax (V)': '36', 'IOTyp (mA)': '16', 'VIOMax (mV)': '5', 'VCCMin (V)': '2', 'VCC Min (V)': '2', 'VCC Max (V)': '36', 'IO Typ (mA)': '16', 'ICC Typ (mA)': '0.4,0.7', 'tres Typ (ns)': '1300', 'VIO Max (mV)': '5', 'TA Min (°C)': '0', 'TA Max (°C)': '70', 'MSL Type': '1,', 'MSL Temp (°C)': '260,235,0', 'ON Target': 'N'",
    "单机用量": 1,
    "默认供应商": "安森美",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/items/3c93a04d5/7759a7431029f97c03abf087749bf738ac566105.pdf",
    "价格": "",
    "替代料": []
  },
  {
    "元件ID": "U6",
    "型号": "PCA9306",
    "零件名称": "I2C",
    "规格描述": "'封装': 'TSSOP-8', 'Input Level': 'CMOS', 'IOMax (mA)': '64', 'VCCMax (V)': '5.5', 'VCCMin (V)': '0', 'Channels': '2', 'tpdMax (ns)': '2'",
    "单机用量": 1,
    "默认供应商": "安森美",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/f_pdf/Manufacturers_Pdf/0ad4c367d04cd3ded451574b2953d08cf564596a.pdf",
    "价格": "",
    "替代料": []
  },
  {
    "元件ID": "U7",
    "型号": "74HC595",
    "零件名称": "SPI",
    "规格描述": "'最高工作温度': '125.0', '封装': 'TSSOP', '最低工作温度': '-40℃', '工作温度': '-40℃~+125.0'",
    "单机用量": 1,
    "默认供应商": "安森美",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/d_pdf/DataSheet_Pdf/d133020483cf609e3e7c853f7f782a0178f6c262.pdf",
    "价格": "",
    "替代料": []
  },
  {
    "元件ID": "U8",
    "型号": "SSD1306",
    "零件名称": "Mipi/Lvds/Edp/Hdmi/RGB/SPI屏",
    "规格描述": "Advance Information128 x 64, Dot Matrix OLED/PLEDSegment/Common Driver with Controller,CMOS",
    "单机用量": 1,
    "默认供应商": "晶门",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/items/7bcff49d9/f3adac08f15ee9c084a5ddc5a1cd230ac3591ef2.pdf",
    "价格": "",
    "替代料": []
  },
  {
    "元件ID": "U9",
    "型号": "TL3301NF100QG",
    "零件名称": "按键/开关",
    "规格描述": "Keypad Switch, KEYPAD SWITCH, SPST, MOMENTARY-TACTILE, 0.05A, 50VDC, 1.47 N, SURFACE MOUNT-STRAIGHT",
    "单机用量": 3,
    "默认供应商": "超威",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/network_download/2022/10/10/1579420640911609858.pdf",
    "价格": "",
    "替代料": []
  },
  {
    "元件ID": "U10",
    "型号": "FDN302P",
    "零件名称": "MOSFET",
    "规格描述": "P 沟道 2.5V 指定 PowerTrench® MOSFET -20V，-2.4A，55mΩ",
    "单机用量": 1,
    "默认供应商": "安森美",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/items/3c93a04d5/f9e0cdbd27bbb1542d7abee87a08d0ac1ebc647d.pdf",
    "价格": 1.09473,
    "替代料": []
  },
  {
    "元件ID": "U11",
    "型号": "TC4427",
    "零件名称": "栅极驱动器",
    "规格描述": "'内部结构': 'Non-Inverting', '最高工作温度': '+125℃', '工作温度': '-40℃~+125℃', '最低工作温度': '-40℃', 'Status': 'In Production', 'Automotive': 'No', 'Driver<br>Type': 'Dual', 'Peak Source Current<br>(A)': '1.5', 'Peak Sink Current<br>(A)': '1.5', 'Maximum Supply Voltage<br>(V)': '18', 'Packages': '8\\\\CERDIP\\n8\\\\DFN-S\\n8\\\\MSOP\\n8\\\\PDIP\\n8\\\\SOIC', 'MOSFET Driver Type': 'Low Side', 'Driver Type': 'Dual', 'Maximum Supply Voltage (V)': '18', 'Peak Source Output (A)': '1.5', 'Peak Sink Output (A)': '1.5', 'Source Resistance (&#937;)': '10', 'Sink Resistance (&#937;)': '10', 'Propagation Delay t<sub>D1</sub> (ns)': '20', 'Propagation Delay t<sub>D2</sub> (ns)': '40', 'Rise Time (t<sub>R</sub>, ns)': '25', 'Fall Time (t<sub>F</sub>, ns)': '25', 'Capacitive Load Drive': '1,000 pF in 25 ns', 'Features': 'lease consider: TC4427A ', 'Peak Source Current A (ampere)': '1.5', 'Peak Sink Current A (ampere)': '1.5', 'Maximum Supply Voltage V (volt)': '18', 'Sink Resistance Ω (ohm)': '10', 'Source Resistance Ω (ohm)': '10', 'Rise Time tR ns (nanosecond)': '25', 'Fall Time tF ns (nanosecond)': '25', 'Propagation Delay tD1 ns (nanosecond)': '20', 'Propagation Delay tD2 ns (nanosecond)': '40'",
    "单机用量": 1,
    "默认供应商": "美国微芯",
    "用户指定": false,
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/items/4b993d962/ae55c85c319ba518a6398ed5924518d98ff3c222.pdf",
    "价格": "",
    "替代料": []
  },
  {
    "元件ID": "U12",
    "型号": "Custom",
    "零件名称": "雾化器",
    "规格描述": "镍铬合金发热丝, 电阻0.5Ω",
    "单机用量": 1,
    "默认供应商": "Custom",
    "用户指定": false,
    "PDF链接": "",
    "价格": "",
    "替代料": []
  }
]
```
# 上面【bom】存在的问题【error】:
    ```
    MAX8630ZETD-T价格可能不存在,
    LTC4099价格可能不存在,
    LTC2494价格可能不存在,
    HC32F052F8TB-LQ32价格可能不存在,
    TL3301NF100QG价格可能不存在,
    TP1价格可能不存在,
    TC4427价格可能不存在,
    67298-3090价格可能不存在，
    ```
# 核心任务
• 当【error】非空时：
  ① PDF链接失效 → 重新验证/获取有效datasheet
  ② 型号可能不存在 → 重新验证该型号信息，如果确定不存在则寻找参数匹配的替代型号
  ③ 价格可能不存在 → 联网查询该元件实时市场单价，即1个元件的价格，单位必须换算为人民币（优先：默认供应商渠道价 → 主流分销商现货价）
  最后，补齐所有集成电路的引脚信息
• 当【error】为空时：
  仅补齐所有器件的价格信息和补齐所有集成电路的引脚信息
• 必做项（所有情况）：
仅当价格或PDF链接缺失的时候补充，不缺失的时候不允许修改价格和PDF链接。
  ① 补齐所有器件的价格信息和PDF链接
  ② 补齐所有集成电路的引脚信息（非集成电路置null）

# datasheet的PDF链接强制要求（违反任一条件即视为无效）
- 扩展名：必须以 .pdf 结尾
- 来源可信度（满足任意一条）：
    官方供应商域名（如 st.com、ti.com、infineon.com）
    权威平台域名（包括但不仅限于）：
    立创系：lceda.cn/jlc.com
    国际平台：mouser.com/digikey.com/octopart.com
- 有效性验证：
    预检查时发送HTTP HEAD请求（非GET）
    必须同时满足：
    状态码 200
    响应头 Content-Type 包含 application/pdf
    文件大小 > 50KB（避免占位页）

# 价格查询
  供应商优先级：
   - 亚德诺元件 → 访问www.analog.com , 检索型号，访问样品及购买页面
   - 美国微芯元件 → 访问www.microchip.com ，检索型号，访问Purchase/Sample页面
   - 其他品牌通过Digi-Key/Mouser/Octopart/立创商城/云汉芯城​​聚合数据，访问购买页面
  如严禁胡编乱造，捏造价格！！
  价格必果查询到价格，则在价格后+空格+来源，来源是查询到价格/单价/price的报价页
  如果查询不到价格，则返回null，须换算成人民币，保留2位小数
  价格必须是1个器件的价格，如果是其它的数量，需要进行换算
    
# 引脚规则：
- 引脚简写规则：连续引脚用简写形式表示，例如："PA0~15"代表的是PA0...PA15共16个引脚
- 相同型号的器件，其对应的引脚完全一致

# 【error】修改说明，错误分为2种：
情况一.PDF链接不可用，这种情况将该型号进行datasheet链接检索。
情况二.型号可能不存在，这种情况将该型号可以先进行联网检索确定是否存在，如果存在则检索datasheet链接和价格,检索不到链接和价格则启动替换并检索datasheet链接、默认供应商和价格;其如果不存在就进行替换，并检索datasheet链接、默认供应商和价格。

# 关键约束
- **严格修改范围**：
  - 仅修改【error】中明确指出的问题器件
  - 非错误器件保留原始所有信息。仅当价格和PDF链接缺失的时候补充，不缺失的时候不允许修改价格和PDF链接。
  - 所有器件都需补充引脚信息
  - 价格缺失的器件都需要补充价格信息
  - PDF链接缺失的器件都需要补充PDF链接信息
- **型号修改规则**：
  - 未在【error】中提到的器件禁止修改型号。仅当价格和PDF链接缺失的时候补充，不缺失的时候不允许修改价格和PDF链接。
  - 替换型号必须满足原规格描述关键参数

# 任务流程
1. 创建问题器件列表：从【error】中提取所有需要修改的元件ID
2. 遍历BOM处理每个器件：
   - if 器件在问题列表中：
       执行PDF链接修复或型号替换流程
       更新规格描述，默认供应商（仅当型号改变时）
       获取验证后的PDF链接
       补充引脚和价格信息
   - else：
       保留原始型号和规格描述
       补充引脚和价格信息（原型号检索）
3. 引脚处理：
   - 集成电路：检索引脚信息并简化表示
   - 非集成电路：显式标注 null
   - 引脚字段长度 ≤ 200字符（超长时精简核心引脚）
4. 价格处理：
   - 所有器件必须补充价格信息
   - 检索失败时显式标注 null
5. PDF链接处理：
   - 长度 ≤ 200字符
   - 验证失败时赋值 null

# 输出规范
1. 数据完整性：
   - 输出BOM长度 == 输入BOM长度
   - 非错误器件保留原始所有字段
2. 字段规范：
   - 错误器件：仅允许修改"型号"、"规格描述"、"PDF链接"、"价格"、"引脚"
   - 非错误器件：仅允许修改"价格"和"引脚"
3. 验证要求：
   - 所有非null的PDF链接必须通过有效性验证
   - 替换型号必须满足原规格描述关键参数
4. 显式标注：
   - 检索失败的字段必须显式输出 null

# 特别注意：
非错误器件保留原始所有信息，仅当价格和PDF链接缺失的时候补充，不缺失的时候不允许修改价格和PDF链接。

# 输出格式
结果按照下面json的格式输出,不需要其他任何信息！！
```json
{{
    "元件ID": "U1",
    "型号": "DS3231",
    "零件名称": "RTC",
    "规格描述": "'工作电压/供电电压范围': '2.3V~5.5V', '工作温度': '-40℃~+85℃', 'ECCN码': 'EAR99', 'VSUPPLY': '2.3 to 5.5', 'Memory Type': 'None', 'Terminal Finish': 'E3', 'AEC-Q': 'No', 'Time Keeping Current': '840', 'Launch Date': '2005-02-04', 'Date/ Time Format': 'YY-MM-DD/ HH:MM:SS', 'Functions': 'RTC', 'EP': 'No', 'Integrated Resonator': 'XTAL', 'Time of Day Alarms': '2', 'Temp Range Code': 'C,E', 'Package': '16-SOIC_W-300_MIL', 'Interface': 'Serial I2C', 'Eval / Ref Circuit': 'Evaluation board', '最高工作温度': '+85℃', '最低工作温度': '-40℃', 'Availability': '2046', 'Date/ Time Format - hh = sec/100': 'YY-MM-DD/ HH:MM:SS', 'Automotive': 'No', 'Temperature Range': '-40 to 85°C', 'Features': 'uP Reset, Power Fail Output, SOIC Package  with Integrated Crystal, Square-Wave Output, TCXO', 'Time Keeping Current (typ) ': '840'",
    "单机用量": 1,
    "默认供应商": "Analog Devices Inc",
    "PDF链接": "https://xcc2.oss-cn-shenzhen.aliyuncs.com/items/07c9ddbd9/46deb6ff544beb0c00f791fc9cc28b9173e66d9f.pdf",
    "价格": "1.23 https://www.analog.com/cn/products/ltc2494/sample-buy.html",
    "替代料": [
      {{
        "evaluate": "完全匹配设计需求，具有超高精度、I2C接口、集成RTC/TCXO/晶体，封装为SOIC-16，工作电压范围2.3V~5.5V，工作温度-40℃~+85℃，符合所有核心参数要求。",
        "replacetitle": "DS3231S/T&R",
        "brandNameCn": "亚德诺"
      }},
      {{
        "evaluate": "近似匹配设计需求，具有I2C接口、集成RTC，封装为SOIC-16，工作电压范围2.3V~5.5V，工作温度-40℃~+85℃，但精度为±5ppm，略低于设计需求的±2ppm。",
        "replacetitle": "DS3231MZ/V+T",
        "brandNameCn": "亚德诺"
      }},
      {{
        "evaluate": "近似匹配设计需求，具有I2C接口、集成RTC，封装为SOIC-8，工作电压范围2.3V~5.5V，工作温度-40℃~+85℃，但封装与设计需求的SOIC-16不完全匹配。",
        "replacetitle": "DS3231MZ/V+",
        "brandNameCn": "亚德诺"
      }},
      {{
        "evaluate": "近似匹配设计需求，具有I2C接口、集成RTC，封装为16-SOIC_W-300_MIL，工作电压范围1.8V~5.5V，工作温度-40℃~+85℃，但精度和功能略低于设计需求。",
        "replacetitle": "DS1339",
        "brandNameCn": "亚德诺"
      }},
      {{
        "evaluate": "近似匹配设计需求，具有I2C接口、集成RTC，封装为16-SOIC_W-300_MIL，工作电压范围1.8V~5.5V，工作温度-40℃~+85℃，但精度和功能略低于设计需求。",
        "replacetitle": "DS1339C",
        "brandNameCn": "亚德诺"
      }}
    ]
  }}
```
         """
         },
    ],
)
print(completion.choices[0].message.content)
if hasattr(completion, "references"):
    print(completion.references)