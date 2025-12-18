"""Forum log test data

Contains minimal examples of various log formats for testing the log parsing functions in ForumEngine/monitor.py.
Logging examples covering the old format ([HH:MM:SS]) and the new format (loguru default format)."""

# ===== Old format (supports [HH:MM:SS]) =====

# Single line JSON, old format
OLD_FORMAT_SINGLE_LINE_JSON = """[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {"paragraph_latest_state": "这是首次总结内容"}"""

# Multiline JSON, old format
OLD_FORMAT_MULTILINE_JSON = [
    "[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "[17:42:31] \"paragraph_latest_state\": \"This is multi-line\\nJSON content\"",
    "[17:42:31] }"
]

# Old format log containing FirstSummaryNode
OLD_FORMAT_FIRST_SUMMARY = """[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - FirstSummaryNode cleaned output: {"paragraph_latest_state": "首次总结"}"""

# Old format log containing ReflectionSummaryNode
OLD_FORMAT_REFLECTION_SUMMARY = """[17:43:00] 2025-11-05 17:43:00.272 | INFO | InsightEngine.nodes.summary_node:process_output:296 - ReflectionSummaryNode cleaned output: {"updated_paragraph_latest_state": "反思总结"}"""

# Old format, non-target node (should be ignored)
OLD_FORMAT_NON_TARGET = """[17:41:16] 2025-11-05 17:41:16.742 | INFO | InsightEngine.nodes.report_structure_node:run:52 - Generating report structure for query"""


# ===== New format (loguru default format) =====

# Single line JSON, new format
NEW_FORMAT_SINGLE_LINE_JSON = """2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {"paragraph_latest_state": "这是首次总结内容"}"""

# Multiline JSON, new format
NEW_FORMAT_MULTILINE_JSON = [
    "2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "2025-11-05 17:42:31.288 | INFO | InsightEngine.nodes.summary_node:process_output:132 - \"paragraph_latest_state\": \"This is multi-line\\nJSON content\"",
    "2025-11-05 17:42:31.289 | INFO     | InsightEngine.nodes.summary_node:process_output:133 - }"
]

# New format log containing FirstSummaryNode
NEW_FORMAT_FIRST_SUMMARY = """2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - FirstSummaryNode cleaned output: {"paragraph_latest_state": "首次总结"}"""

# New format log containing ReflectionSummaryNode
NEW_FORMAT_REFLECTION_SUMMARY = """2025-11-05 17:43:00.272 | INFO | InsightEngine.nodes.summary_node:process_output:296 - ReflectionSummaryNode cleaned output: {"updated_paragraph_latest_state": "反思总结"}"""

# New format, non-target nodes (should be ignored)
NEW_FORMAT_NON_TARGET = """2025-11-05 17:41:16.742 | INFO | InsightEngine.nodes.report_structure_node:run:52 - Generating report structure for query: China Molybdenum expected stock price changes"""

# New format, ForumEngine log
NEW_FORMAT_FORUM_ENGINE = """2025-11-05 22:31:09.964 | INFO | ForumEngine.monitor:monitor_logs:457 - ForumEngine: Forum is being created..."""


# ===== Complex JSON example =====

# JSON containing updated_paragraph_latest_state (this should be extracted first)
COMPLEX_JSON_WITH_UPDATED = [
    "2025-11-05 17:43:00.272 | INFO | InsightEngine.nodes.summary_node:process_output:296 - Cleaned output: {",
    "2025-11-05 17:43:00.273 | INFO | InsightEngine.nodes.summary_node:process_output:297 - \"updated_paragraph_latest_state\": \"## Core Discovery (Updated Version)\\n1. This is the updated content\""ersion)\\n1. This is the updated content\"",
    "2025-11-05 17:43:00.274 | INFO     | InsightEngine.nodes.summary_node:process_output:298 - }"
]

# JSON with only paragraph_latest_state
COMPLEX_JSON_WITH_PARAGRAPH = [
    "2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "2025-11-05 17:42:31.288 | INFO | InsightEngine.nodes.summary_node:process_output:132 - \"paragraph_latest_state\": \"## Overview of core findings\\n1. This is the first summary of content\""ngs\\n1. This is the first summary of content\"",
    "2025-11-05 17:42:31.289 | INFO     | InsightEngine.nodes.summary_node:process_output:133 - }"
]

# JSON content containing newline characters
COMPLEX_JSON_WITH_NEWLINES = [
    "[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "[17:42:31] \"paragraph_latest_state\": \"First line of content\\nSecond line of content\\nThird line of content\"",
    "[17:42:31] }"
]

# ===== Boundary cases =====

# Lines that do not contain "sanitized output" (should be ignored)行（应该被忽略）
LINE_WITHOUT_CLEAN_OUTPUT = """2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - JSON parsed successfully"""

# Contains "sanitized output" but not in JSON format不是JSON格式
LINE_WITH_CLEAN_OUTPUT_NOT_JSON = """2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: This is not in JSON format"""

# blank line
EMPTY_LINE = ""

# Rows with only timestamps
LINE_WITH_ONLY_TIMESTAMP_OLD = "[17:42:31]"
LINE_WITH_ONLY_TIMESTAMP_NEW = "2025-11-05 17:42:31.287 | INFO | module:function:1 -"

# Invalid JSON format
INVALID_JSON = [
    "2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "2025-11-05 17:42:31.288 | INFO | InsightEngine.nodes.summary_node:process_output:132 - \"paragraph_latest_state\": \"missing closing quote",
    "2025-11-05 17:42:31.289 | INFO | InsightEngine.nodes.summary_node:process_output:133 - }"
]

# ===== Mixed formats (both old and new formats in the same batch of logs) =====
MIXED_FORMAT_LINES = [
    "[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "2025-11-05 17:42:31.288 | INFO | InsightEngine.nodes.summary_node:process_output:132 - \"paragraph_latest_state\": \"Mixed format content\"",
    "[17:42:31] }"
]

# ===== Actual production environment log example =====

# QueryEngine reflection summary - multi-line JSON format
REAL_QUERY_ENGINE_REFLECTION = [
    "[10:56:04] 2025-11-06 10:56:04.759 | INFO | QueryEngine.nodes.summary_node:process_output:302 - Cleaned output: {",
    "[10:56:04] \"updated_paragraph_latest_state\": \"CMOC (CMOC) is the leading molybdenum producer in mainland China and one of the world's top producers of non-ferrous metals and rare metals. The company's predecessor can be traced back to the small mineral processing plant in Luanchuan County established in 1969 with the approval of the former Ministry of Metallurgy. In 1999, Luoyang Luanchuan Molybdenum was established The group was formally established and restructured into a joint-stock company in 2006. After two mixed-ownership reforms in 2004 and 2014, CMOC is currently a privately held joint-stock company listed on the Hong Kong Stock Exchange in 2007 (stock code: 03993), and returned to A-share listings in 2012. Listed on the Shanghai Stock Exchange (stock code: 603993). \\n\\nLuoyang Molybdenum's core business covers the mining, selection, smelting and processing of basic metals and rare metals, including molybdenum, tungsten, copper, cobalt, niobium, phosphorus, etc. The company's business footprints span Asia, Africa, South America and Europe, and it is a global leader. is a manufacturer of copper, cobalt, molybdenum, tungsten and niobium, and is also the leading phosphate fertilizer manufacturer in Brazil. As of the third quarter of 2025, the company has achieved operating income of 145.485 billion yuan, net profit attributable to shareholders of 8.671 billion yuan, operating net cash flow of 12.009 billion yuan, and the asset-liability ratio has been further optimized to 50.15%. Strategy and Operation Upgrading \\nThe company will usher in an important strategic turn in 2025 and introduce a management team with an international perspective. New Chairman Liu Jianfeng (former Commercial Director of China National Offshore Oil Corporation) and Executive Vice President Que Chaoyang (former senior executive of Zijin Mining Group) will take the lead in promoting organizational structure innovation through the acquisition of the Cangrejos gold mine in Ecuador (expected to be put into production in 2029). Through key mergers and acquisitions, the asset portfolio has been transformed into a multi-variety (mainly copper and gold), multi-country (covering Africa, South America), and multi-stage (combination of production and greenfield projects). The core mining area of the Democratic Republic of the Congo has been continuously optimized through "small reforms", and the planned copper production capacity will reach 800,000-1 million tons in 2028. The construction of Nzilo II hydropower station effectively alleviates energy constraints. Industry status and financial performance\nAccording to the latest ranking of China's Fortune 500 in 2025, China Molybdenum ranks 138th with revenue of 213.029 billion yuan, and its market value exceeds 250 billion yuan. The company has created a unique "mining + trade" two-wheel model, and the IXM trading platform controls 12% of the world's copper concentrate trade volume. TFM and KFM project costs have entered the top 30% and top 10% of the world respectively. The new energy metal field maintains an absolute advantage, with cobalt production capacity accounting for more than 40% of the world. The recent export control policy of the Democratic Republic of the Congo has prompted a rebound in cobalt prices, with the average price in the first half of 2025 increasing by 26% compared with 2024. Technology and Social Responsibility\nThe 5G smart mine realizes unmanned operation of the entire process of drilling, transportation and crushing, and the mining cost is 18-22% lower than that of international peers. In terms of ESG construction, the MSCI rating is upgraded to BBB level, climate risks are disclosed through the TCFD framework, the mine electrification rate is 35%, and the emission reduction intensity is reduced by 19%. In 2025, a cash dividend of 0.255 yuan per share will be implemented to continue to reward shareholders. Future Outlook\nManagement expects to maintain high-intensity mergers and acquisitions from 2026 to 2028, focusing on copper and gold resources, and has reserved multiple potential projects for the Cangrejos gold mine in Ecuador (estimated annual gold production of 11.5 tons) and KF. The second phase of the M expansion will constitute a medium-term growth pole. Morgan Stanley predicts that the copper equivalent production capacity will exceed 1.5 million tons in 2027. The company's asset-liability ratio is controlled within the 50% safety line, and its cash on hand exceeds 32 billion yuan, providing sufficient ammunition for strategic layout."jects). The core mining areas of the Democratic Republic of the Congo continue to optimize through "small reforms". The planned copper production capacity will reach 800,000-1 million tons in 2028. The construction of Nzilo II hydropower station effectively alleviates energy constraints. \\n\\n### Industry status and financial performance\\nAccording to the latest ranking of the Fortune China 500 in 2025, China Molybdenum jumped to 138th with revenue of 213.029 billion yuan, and its market value exceeded 250 billion yuan. The company has created an original two-wheel model of "mining + trade". The IXM trading platform controls 12% of the world's copper concentrate trade volume, and the TFM and KFM project costs have entered the top 30% and top 10% of the world respectively. The field of new energy metals maintains an absolute advantage, with cobalt production capacity accounting for more than 40% of the world. The recent export control policy of the Democratic Republic of the Congo has prompted a rebound in cobalt prices, with the average price in the first half of 2025 increasing by 26% compared with 2024. \\n\\n### Technology and Social Responsibility\\n5G smart mine realizes the entire process of perforation, transportation and crushing unmanned, and the mining cost is 18-22% lower than that of international peers. In terms of ESG construction, the MSCI rating was upgraded to BBB, climate risks were disclosed through the TCFD framework, the mine electrification rate was 35%, and the emission reduction intensity dropped by 19% year-on-year. A cash dividend of RMB 0.255 per share will be implemented in 2025 to continue giving back to shareholders. \\n\\n### Future Outlook\\n Management expects to maintain high-intensity mergers and acquisitions from 2026 to 2028, focusing on copper and gold resources, and has reserved multiple potential projects. Ecuador's Cangrejos gold mine (estimated to produce 11.5 tons of gold per year) and KFM's second phase expansion constitute a medium-term growth pole. Morgan Stanley predicts that copper equivalent production capacity will exceed 1.5 million tons in 2027. The company's asset-liability ratio is controlled within the 50% safety line, and cash on hand exceeds 32 billion yuan, providing sufficient ammunition for strategic layout. \"",
    "[10:56:04] }"
]

# InsightEngine Reflection Summary - Multi-line JSON format (contains "Generating Reflection Summary" flag)eflection summary"标识）
REAL_INSIGHT_ENGINE_REFLECTION = [
    "[10:55:19] 2025-11-06 10:55:19.563 | INFO | InsightEngine.nodes.summary_node:run:265 - Generating reflection summary",
    "[10:56:41] 2025-11-06 10:56:41.626 | INFO | InsightEngine.nodes.summary_node:process_output:296 - Cleaned output: {",
    "[10:56:41] \"updated_paragraph_latest_state\": \"## 核心发现（更新版）\\n洛阳钼业2025年第三季度市场表现呈现结构性分化，在全球铜价同比上涨18%（LME三个月期铜均价$8,927/吨）的背景下，公司股价却累计下跌12.3%，与申万有色金属指数7.8%的涨幅形成鲜明对比。深入分析显示，这种背离主要源于三大矛盾：全球能源转型红利与区域性运营风险的博弈、资源禀赋优势与ESG短板的冲突、以及机构估值框架转变与散户认知滞后的错位。最新舆情监测发现，专业投资者讨论焦点已从产量数据转向刚果（金）社区索赔案件的司法进展（涉及金额预估2.3亿美元），而散户仍在热议『新能源金属』概念炒作。\\n\\n## 详细数据画像\\n### 产量与成本\\n- 刚果（金）TFM铜钴矿：Q3铜产量12.8万吨（环比-7%），钴产量5,200吨（环比-9%），单位现金成本升至$1.52/lb（Q2为$1.38），因当地罢工导致14天停产（损失产值约3.2亿元）\\n- 巴西铌磷矿：铌铁产量2.1万吨（同比+4%），磷肥产量28万吨（创纪录），海运费用占比升至23%（2024年平均17%），但因巴西雷亚尔贬值节约本地成本1.8亿元\\n- 澳洲NPM铜金矿：铜品位下滑至0.72%（上年同期0.81%），但通过提高回收率维持产量稳定（回收率提升2.3个百分点至89.7%）\\n\\n### 财务指标\\n- 营收：Q3实现287亿元（同比+9.2%，环比-5.3%），低于彭博一致预期6%，主因铜钴销量下滑\\n- 现金流：经营活动现金流净额42亿元（同比-18%），资本开支达35亿元（KFM项目占72%）\\n- 负债：资产负债率升至58.3%（2024年末54.1%），新增20亿元公司债票面利率6.8%（较同行高120bp）\\n\\n### 市场反应\\n- 股价表现：三季度累计换手率287%，显著高于紫金矿业（189%）和江西铜业（156%），振幅达43%\\n- 机构动向：北向资金持仓减少1.2亿股，挪威养老基金持股比例从2.1%降至1.4%（ESG调仓）\\n- 舆情热度：百度指数『洛阳钼业』日均搜索量3,215次（同业排名第4），但专业平台Wind词频统计显示分析师关注度排名第2（含327份研报）\\n\\n## 多元声音汇聚\\n产业视角：\\n1. 【Fastmarkets分析师】『刚果（金）新矿业税实施后，TFM项目有效税率从31.5%升至35.8%，每磅铜的税负增加$0.12』（报告被引用87次）\\n2. 【巴西矿业协会】『尽管海运成本上升，洛阳钼业的铌磷矿仍是全球成本曲线左端20%的优质资产』\\n3. 【刚果矿业部长声明】『要求外资矿业企业本地采购比例需在2026年前达到40%』（现行25%）\\n4. 【澳洲矿产委员会】『NPM矿的劳工成本已超出可承受范围，可能影响2026年扩产计划』\\n\\n投资者声音：\\n5. 【雪球用户@价值挖掘机】『DCF模型显示，若刚果政策风险溢价上调200bp，公司合理估值应下调15-20%』（附详细测算表格，获专业认证）\\n6. 【股吧热帖】『社保基金三季报减持后，融资余额反而增加4.3亿元，多空博弈激烈』（单日点击量超10万）\\n7. 【推特机构账号】『MSCI将公司治理(G)评分从6.2降至5.4，主因董事会独立性问题』\\n8. 【机构投资者调研纪要】『至少7家基金质疑刚果子公司分红政策（近三年分红率仅12%）』\\n9. 【Reddit散户讨论】『看涨期权持仓量暴增300%，集中行权价9元』\\n\\n国际视角：\\n10. 【彭博社报道】『洛阳钼业与嘉能可的KFM项目股权谈判陷入僵局，双方对2026年后钴价预期差异达$5/lb』\\n11. 【刚果当地媒体】『TFM周边社区新提起3起环境诉讼，要求赔偿金合计8,000万美元』\\n12. 【澳洲矿业工人论坛】『NPM矿区的工会正酝酿新一轮薪资谈判，现有合同溢价已达行业平均125%』\\n13. 【路透社】『中国进出口银行可能为KFM项目提供15亿美元再融资』\\n14. 【非洲发展银行报告】『刚果矿业社区冲突事件同比增加47%』\\n\\n## 深层洞察升级\\n### 政策风险量化\\n通过蒙特卡洛模拟测算，在以下情境下：（1）刚果 royalty rate 上调3个百分点（2）海运成本维持当前水平（3）钴价徘徊在$25/lb，公司2026年EBITDA可能缩水23-28亿元。敏感性分析显示，刚果政策变量对估值影响权重从去年的18%升至31%。地缘政治专家指出，刚果大选临近使矿业政策不确定性指数达78（警戒线70）。\\n\\n### ESG影响拆解\\n- 环境(E)：尾矿库管理被MSCI标红，主要因刚果项目的水循环利用率仅72%（国际同行平均85%），且2025年发生2次小规模渗漏\\n- 社会(S)：社区关系评分暴跌，源于Q3当地雇佣比例降至43%（承诺目标60%），且医疗投入同比减少15%\\n- 治理(G)：董事会中独立董事占比33%（仅1名具国际矿业经验），低于国际矿业公司平均45%的水平\\n\\n### 资金行为解析\\n龙虎榜数据显示，三季度机构专用席位净卖出23亿元（创历史季度纪录），但同时量化基金交易占比从12%升至19%，显示算法交易对股价波动增强效应。北向资金持仓成本分析表明，外资止损线集中在6.8元附近（现价7.2元）。值得注意的是，大宗交易溢价率从Q2的-3%收窄至-1.2%，暗示部分长线资金开始逢低吸纳。\\n\\n## 趋势和模式识别\\n1. 信息分层加剧：专业机构通过LME库存数据（近期亚洲仓库铜库存增加35%）预判供需变化，而散户仍依赖券商研报的乐观预测（『买入』评级占比仍达68%但较Q2下降11%）\\n2. ESG因子定价权提升：负面评级直接导致11月3日股价跳空低开3.2%，创三个月最大单日缺口\\n3. 多空博弈新特征：融券余额历史首次突破5亿元（日均利率达8.6%），同时场外期权隐含波动率升至52%（高于行业平均38%）\\n4. 成本通胀传导滞后：虽然硫酸等辅料价格上涨23%，但产品售价仅提升9%，毛利率承压明显\\n\\n## 对比分析\\n| 维度                | 洛阳钼业               | 紫金矿业               | 江西铜业               | 行业平均               |\\n|---------------------|------------------------|------------------------|------------------------|------------------------|\\n| 海外营收占比        | 68%                    | 55%                    | 32%                    | 48%                    |\\n| 铜矿现金成本        | $1.52/lb               | $1.35/lb               | $1.48/lb               | $1.45/lb               |\\n| ESG评级             | BB-(MSCI)              | BBB(S&P)               | BB+(MSCI)              | BBB-(S&P)              |\\n| Q3机构调研次数      | 87次                   | 126次                  | 53次                   | 89次                   |\\n| 散户持股比例        | 41%                    | 38%                    | 45%                    | 42%                    |\\n| 海外项目纠纷数      | 4起                    | 2起                    | 1起                    | 2.3起                  |\\n| 研发投入占比        | 0.8%                   | 1.2%                   | 0.9%                   | 1.1%                   |\\n\\n*数据周期：2025年第三季度，来源：公司公告、各评级机构、沪深交易所、彭博终端*\"",
    "[10:56:41] }"
]

# MediaEngine Reflection Summary - Single Line JSON Format
REAL_MEDIA_ENGINE_REFLECTION = """[10:56:15] 2025-11-06 10:56:15.779 | INFO | MediaEngine.nodes.summary_node:run:268 - Generating reflection summary
[10:56:42] 2025-11-06 10:56:42.337 | INFO | MediaEngine.nodes.summary_node:process_output:302 - Cleaned output: {"updated_paragraph_latest_state": "## 综合信息概览\\r\\n根据当前查询需求，本段将围绕洛阳钼业的基本情况展开分析，重点涵盖其公司成立时间、总部位置、主营业务以及在全球矿业领域的地位。尽管本次提供的搜索结果为空，但基于对公开权威信息的掌握和行业常识，结合企业官网、年报及主流财经媒体的历史报道，可以系统性地还原洛阳钼业的核心概况。作为全球领先的多元化矿业集团，洛阳钼业在中国乃至世界有色金属行业中占据重要地位，其发展历程、战略布局与资源控制能力均体现出显著的国际化特征。\\r\\n\\r\\n## 文本内容深度分析\\r\\n洛阳钼业全称为洛阳栾川钼业集团股份有限公司，成立于2003年，其前身可追溯至1969年建立的栾川钼矿，标志着企业在钼钨资源开发领域拥有深厚的历史积淀。公司于2007年在香港联交所主板上市（股票代码：03993.HK），并于2012年在上海证券交易所主板上市（股票代码：603993），形成A+H股双资本平台格局，增强了融资能力和国际影响力。总部位于河南省洛阳市栾川县，地处中国中部重要的矿产资源富集区，依托当地丰富的钼、钨等战略金属储量，构建了从采矿、选矿到深加工的一体化产业链。公司的主营业务聚焦于基本金属和稀有金属的勘探、开采、加工与销售，核心产品包括钼、钨、铜、钴、铌、磷以及黄金等，形成了多元化的矿产品组合，有效提升了抗周期波动的能力。尤其在钼资源方面，洛阳钼业拥有的栾川矿区被誉为'世界三大钼矿之一'，其钼金属储量位居全球前列；而在钨资源方面也具备世界级规模，是中国乃至全球最重要的钨生产商之一。近年来，通过一系列跨国并购，公司成功拓展至非洲和南美市场，特别是在刚果（金）运营的Tenke Fungurume铜钴矿，使其成为全球第二大钴生产商，在新能源电池原材料供应链中占据关键地位。此外，公司在巴西持有的铌矿（Catalão和Boa Vista项目）同样是全球高品位铌资源的重要供应源，铌广泛应用于高强度合金钢制造，服务于航空航天与高端装备制造领域。\\r\\n\\r\\n## 视觉信息解读\\r\\n虽然本次未提供相关图片资料，但从以往公开发布的公司宣传材料、年报封面及矿山实景图中可以推断出，洛阳钼业的品牌视觉通常以深蓝、灰色为主色调，象征着工业稳重与科技感，配以矿山开采场景、现代化选矿厂或地球仪元素，突出其'全球化矿业巨头'的定位。例如，在年度报告中常见大型露天矿坑航拍图，展现宏大的开采规模；也有员工在智能化控制中心监控生产流程的画面，体现数字化转型成果。这些视觉符号共同塑造了一个传统资源型企业向高科技、绿色化、国际化综合矿业集团转型的形象。若能获取近期官方发布的图片，预计将看到更多关于绿色矿山建设、生态修复工程以及海外项目本地社区合作的内容，反映ESG（环境、社会与治理）理念的深入实践。\\r\\n\\r\\n## 数据综合分析\\r\\n从财务与运营数据来看，洛阳钼业近年来保持稳健增长态势。根据2023年年报显示，公司全年实现营业收入约1,445亿元人民币，归母净利润超过80亿元，资产总额逾2,000亿元，展现出强大的盈利能力和资产实力。在资源储量方面，据JORC标准披露，公司控制的钼金属储量超过200万吨，钨储量约80万吨，铜资源量达数千万吨级别，钴资源量亦达数百万吨，资源禀赋极为优越。产量方面，2023年公司年产钼约1.7万吨、钨精矿折合WO₃约2.5万吨、铜金属约22万吨、钴金属约2.5万吨，其中铜钴产量主要来自刚果（金）和澳大利亚Northparkes项目。在全球矿业排名中，洛阳钼业连续多年入选《福布斯》全球企业2000强，并在《财富》中国500强中位列前茅。据SNL Metals & Mining等机构统计，其钴产量市场份额约占全球总产量的15%-18%，仅次于嘉能可（Glencore），居世界第二位；而钼产品的市场占有率同样位居全球前三。此外，公司研发投入持续增加，2023年研发费用超15亿元，主要用于智能矿山建设、低品位矿石综合利用技术及碳减排工艺优化，体现了向高质量发展模式转型的决心。\\r\\n\\r\\n## 多维度洞察\\r\\n综上所述，洛阳钼业不仅是一家根植于中国河南的地方性矿业企业，更已发展为具有全球资源配置能力的跨国矿业集团。其成功路径体现出'立足本土优势资源+战略性海外扩张'的双轮驱动模式。在国内，依托栾川世界级钼钨矿床建立了稳固的基本盘；在海外，通过精准并购实现了对关键战略矿产——尤其是新能源所需铜钴资源——的有效掌控，契合全球能源转型趋势。与此同时，公司积极推进数字化、智能化和绿色矿山建设，如在北秘鲁的Kisanfu铜钴矿采用无人驾驶运输系统和远程监控平台，提升安全与效率。未来，随着电动汽车、储能系统和可再生能源基础设施对铜、钴、铌等金属需求的持续攀升，洛阳钼业的战略价值将进一步凸显。然而，其海外运营也面临地缘政治风险、环保合规压力及社区关系管理等挑战，尤其是在刚果（金）等资源丰富但治理相对薄弱的国家。因此，如何平衡经济效益与社会责任、强化可持续发展能力，将是决定其长期竞争力的关键所在。"}"""

# ===== SearchNode output example (should be filtered and should not enter the forum) =====

# SearchNode first search query - multi-line JSON format
SEARCH_NODE_FIRST_SEARCH = [
    "[11:16:35] 2025-11-06 11:16:35.567 | INFO | InsightEngine.nodes.search_node:process_output:97 - Cleaned output: {",
    "[11:16:35] \"search_query\": \"What do you think\"",
    "[11:16:35] \"search_tool\": \"search_topic_globally\"",
    "[11:16:35] \"reasoning\": \"This is the reasoning of the search query\"",
    "[11:16:35] \"enable_sentiment\": true",
    "[11:16:35] }"
]

# SearchNode reflects on search queries - single line JSON format
SEARCH_NODE_REFLECTION_SEARCH = """[11:17:05] 2025-11-06 11:17:05.547 | INFO | InsightEngine.nodes.search_node:process_output:232 - Cleaned output: {"search_query": "AI教育 数据泄露 不公平", "search_tool": "search_hot_content", "reasoning": "需要了解近期关于AI教育的热点争议，特别是公众最关心的数据安全和公平性问题，以补充具体案例和真实舆情数据", "time_period": "week", "enable_sentiment": true}"""

# ===== Error log example (should be filtered and should not enter the forum) =====

# SummaryNode's JSON parsing failure error log
SUMMARY_NODE_JSON_ERROR = "[11:55:31] 2025-11-06 11:55:31.763 | ERROR | MediaEngine.nodes.summary_node:process_output:141 - JSON parsing failed: Unterminated string starting at: line 1 column 28 (char 27)"

# SummaryNode's JSON repair failure error log
SUMMARY_NODE_JSON_FIX_ERROR = "[11:55:31] 2025-11-06 11:55:31.799 | ERROR | MediaEngine.nodes.summary_node:process_output:149 - JSON repair failed, use the cleaned text directly"

# ERROR level log for SummaryNode (contains nodes.summary_node but should not be captured)
SUMMARY_NODE_ERROR_LOG = "[11:55:31] 2025-11-06 11:55:31.763 | ERROR | MediaEngine.nodes.summary_node:process_output:141 - An error occurred: Unable to process output"

# Traceback error log for SummaryNode (although nodes.summary_node is included, it should not be captured)
SUMMARY_NODE_TRACEBACK = """[11:55:31] File "D:\\Programing\\BettaFish\\SingleEngineApp\\..\\MediaEngine\\nodes\\summary_node.py", line 138, in process_output
[11:55:31] result = json.loads(cleaned_output)"""

