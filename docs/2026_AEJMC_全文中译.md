# 别太冷静：视觉与文本框架的组合如何影响短视频评论区中的愤怒表达？

短视频平台已经成为公共议题传播的重要场域。许多原本属于政策讨论或制度解释的问题，在进入平台之后，往往不再以平稳的信息形态流通，而是迅速被转化为带有情绪张力的内容。在这些外显情绪之中，愤怒尤其值得关注。它通常伴随着明显的责任归因与道德评判，并进一步强化情绪本身。因此，在涉及制度边界或公共安全的话题中，愤怒往往比其他情绪更容易被触发，也更容易被平台机制放大（Rico et al., 2017）。

正因如此，一个看似简单却至关重要的问题随之出现：为什么围绕同一公共议题的不同短视频，会在评论区激起强度悬殊的愤怒反应？如果议题本身的争议性已经相对明确，那么评论区情绪差异究竟仍主要取决于议题本身，还是更深地受到视频内容组织方式的影响？这个问题不仅关系到我们如何理解短视频时代公共情绪的形成机制，也关系到平台中的内容生产者如何通过多模态设计塑造讨论方向与情绪基调。

中国“吸毒记录封存”议题为观察这一问题提供了一个合适的案例。2025年11月至12月间，随着《中华人民共和国治安管理处罚法》修订案明确提出“违反治安管理的记录应当予以封存”，以及“吸毒记录也属于封存范围”的信息被媒体集中报道，这一议题迅速在舆论场中升温，其热度超过了同期98%的社会热点议题。在中国长期实行严厉禁毒政策、公众对毒品问题高度敏感的社会语境下，这一议题很容易从制度解释迅速外溢为有关公平与道德边界的情绪性争论。然而，正如后文分析将显示的那样，并非所有相关短视频都会以同样强度激起愤怒反应。

框架理论为理解这一问题提供了一个重要起点。然而，与框架对认知和行为的作用相比，框架与情境性情绪表达之间的关系仍缺乏直接检验。其次，近年来的研究开始逐渐认识到视觉框架的重要性，也指出视觉与文本之间的关系会改变传播效果（Dan, 2017）。但现有大多数成果主要集中在新闻图片或图文材料上，对于短视频这类连续、动态对象中的视觉框架究竟应如何识别，视觉与文本如何组合，以及这种组合是否会进一步影响评论区中的愤怒表达，仍然缺乏充分回答。

本文正试图在这一理论缺口上作出贡献。得益于视觉传播领域计算方法的进展，以及大语言模型（LLM）图像识别能力的逐步成熟（Peng et al., 2024），本文提出了一种用于测量动态视频中视觉框架的分析方法。随后，本文以449个与中国“吸毒记录封存”争议相关的抖音短视频为样本进行实证检验，成功识别出三类可供比较的主导视觉框架，并采用相同的计算方法对其文本框架进行编码，同时利用机器学习识别相关短视频评论区中的愤怒表达，并将其作为回归分析的因变量。

数据结果表明，视觉框架在情绪设定中具有优先作用，不同的视觉—文本框架组合能够显著对应不同水平的愤怒表达，而它们之间的一致性也会影响评论区中的愤怒表达。这意味着，多模态关系比单一模态更能解释评论区情绪差异。受众情绪受到影响，不仅取决于“展示了什么”或“说了什么”，也取决于“呈现方式与叙事方式是如何被组合起来的”。

## 文献综述

### 短视频平台中的公共议题传播与情绪互动

在新媒体传播时代，短视频深刻重塑了公共议题的讨论模式与公众参与路径。以抖音为代表的短视频平台，已经逐渐成为意见生成与传播互动的重要场域（Yu et al., 2023）。不同于传统新闻文本或单纯的图文报道，短视频平台呈现出一种碎片化、娱乐化且容易被算法逻辑驱动的互动生态，这使得公共议题更容易被嵌入日常信息流之中，并被注意、消费（Liang & Ye, 2025; O’Brien et al., 2025）。

受平台经济与算法逻辑影响，相较于传统信息交换媒介，短视频传播者更倾向于将公共议题包装为带有主观意志的互动对象，以争夺注意力——带有情绪张力的内容比保持事实本身、强调理性、中立与客观的评论更能吸引注意（Van Dijck et al., 2018; Eberl et al., 2020）。已有研究表明，在以注意力和互动为中心的社交媒体分发逻辑面前，传播主体往往会有意识地增强内容的情绪性，例如利用温和的语言特征影响用户订阅（Chen, 2025），通过匹配焦虑和愤怒的语调吸引回复（Lee & Britt, 2024），以及诱导点击（Zhang & Fu, 2022）。

尽管在柏拉图传统中，情绪通常不被视为可靠的判断基础，而更常被理解为需要由理性节制和引导的心理力量，但在现代认知心理学层面，情绪事实上会对议题与事件的感知和评价产生强烈影响（Kühne et al., 2011），并影响信息处理过程（Kühne & Schemer, 2015）。尤其在争议性公共议题中，受众在面对相关内容时，往往并不是先形成系统而稳定的政策判断，而是先产生强弱不等的情绪反应（Hasell et al., 2025）。在这样的背景下，理解传播主体是否、以及如何试图影响受众情绪，就显得尤为重要。

随着情绪研究的深入，学者们开始比较不同情绪类别在传播效果中的作用。研究发现，当某项政策被感知为违背了共同体整体意志时，愤怒表达尤为突出（Wayne, 2023）。一方面，愤怒是一种高唤醒、强归因的离散情绪，通常与不公感、责任追究、道德谴责以及惩罚倾向密切相关，因此在涉及风险、失范、纵容或制度争议的话题中更容易被激发（Montada & Schneider, 1989）。另一方面，与悲伤或无助等负面情绪相比，愤怒更具可见性和可传播性，也更容易转化为直接评论、转发、情绪动员，甚至集体行动（Valenzuela et al., 2017; Van Zomeren et al., 2004）。

在“中国吸毒记录封存”这一同时涉及制度边界与反对意见的话题中，考察相关内容如何触发愤怒，是理解其传播后果的一条关键路径。与此同时，也不难观察到：即便围绕的是同一公共议题，不同短视频仍然可能激发出强度不同的愤怒反应。也就是说，在面对同一受众、同一时空环境时，为什么同一议题下的不同短视频会激发出不同水平的愤怒，已经成为一个有待解释的问题。

本文认为，关键不仅在于议题本身是否具有争议性，更在于传播者如何借助特定的内容组织方式对议题进行情绪化建构，而短视频所激发的愤怒程度，实际上与前端内容如何被整合密切相关。

框架理论指出，媒体并不是机械地传递事实，而是通过对特定信息元素的选择、凸显与省略，构造出一种特定的意义结构，并引导受众按照预设方式理解与解释问题，从而推动特定的问题定义、因果解释、道德评价和处理建议，进而影响受众的认知，乃至情绪与行动（Entman, 1993）。换言之，如果相似短视频所激发的情绪反应呈现出层级性与系统性差异，那么这种差异就有必要追溯到视频本身的内容结构，也就是它由何种框架构成。

### 框架效应与愤怒表达

自Goffman提出“框架”概念以来，框架理论逐渐成为传播研究中解释媒体如何建构现实与塑造意义的重要理论资源（Goffman, 1974）。借助框架理论，我们可以更好地理解媒体建构社会现实的过程，以及它在塑造公众对特定事件或议题的认知和态度方面所发挥的有限作用。以争议性报道为例，媒体可以采用相对温和的框架，也可以采用更具威胁感和归责取向的框架（Ekström & Shehata, 2024）。在科技报道中，媒体可能采用强调创新与经济效率的“进步框架”，强调警示与伦理忧虑的“风险框架”，或者突出国际竞争的“竞争框架”，从而塑造公众对技术的差异化认知（Weaver et al., 2009）。将这一思路延伸到自媒体平台，框架依然是描述创作者如何影响公共讨论的重要概念。

从媒介心理学角度看，当受众接触到某种特定框架时，该框架会激活既有认知图式，提高被强调信息的心理可得性与显著性，并由此影响受众的感觉、情绪、认知与行为（Geise & Xu, 2025）。其情绪效应，尤其是对愤怒的影响，主要经由三条路径发挥作用：责任归因、风险建构与受害者呈现。当内容明确指出谁应当负责、谁造成了伤害时，受众更容易形成道德谴责，进而体验到愤怒（Kühne et al., 2015）。当某个议题被呈现为高度威胁且充满不确定性时，受众更容易进入高度警觉状态，而这为愤怒提供了基础（Nabi, 2003）。与此同时，对受害者的视觉呈现会强化受众对不公与伤害的感知，从而加强其对被认为应负责任一方的愤怒（Dawtry et al., 2020）。这三条路径在同一传播单元中相互交织，共同塑造受众情绪的方向与强度。然而，相关综述也指出，尽管经验研究已经开始关注视觉框架的情感维度，但现有不少文献，包括上述研究在内，并未将受众的情感反应本身视为核心结果变量，而是更多把情绪看作通向认知等后续效应的中介变量（Xu, 2025）。换言之，关于框架如何直接关联到受众的外显情绪表达，尤其是在平台化互动环境中的外显情绪表达，仍然缺乏更充分的经验检验。

在社交媒体时代，评论区为观察这种情绪反应提供了一个相对可见的场域。尽管大多数视频观众往往保持沉默，而评论者也不能完全代表整体受众（Sun et al., 2014），但评论区仍然是平台上少数能够让外显情绪表达集中出现并被观察到的空间。因此，本文将评论区中的愤怒表达视为框架情绪效应的一个可观察指标，并用它来检验不同内容组织方式是否系统性地对应于不同强度的愤怒反应（Humprecht et al., 2020）。

但在测量短视频中框架对情绪的影响之前，还必须首先回答一个更基础的问题：在短视频传播中，究竟什么构成了框架？

### 从文本到图像再到视频

自古腾堡时代以来，学术传统往往赋予书写文字以文化上的首要地位，并将其视为人类思想最优越的载体。这种取向自然影响了早期框架研究，使其主要聚焦于文本信息，并把新闻标题或政治宣传中的叙事修辞与组织模式，视为识别框架的主要入口。结果是，框架研究发展出了一套以文本模态为中心、相对成熟的方法论传统。然而，随着当代人文社会科学中的“视觉转向”，图像、视频以及其他视觉材料在意义生产中的作用日益受到重视（Mitchell, 1994）。与此同时，当代媒体内容中动态图像信息的普遍增长，尤其是在短视频平台上，使得仅通过语言表征来识别说服性框架，越来越显得不足。

事实上，视觉传播的联想逻辑与文本传播的线性推理逻辑有显著差异。视觉更依赖并行式、启发式的信息处理，而文本通常以更为顺序化的方式被处理（Messaris, 2003）。此外，在同一时间单位内，图像能够传递的信息往往多于文字，这使得观看者可以以相对自动、整体的方式接近意义（Coleman, 2010）。因此，视觉拥有自身相对完整且独立的意义系统（Kress & van Leeuwen, 2020）。与文本相比，视觉也更能吸引注意并激发更强烈的情绪反应（Iyer & Oldmeadow, 2006; Mendelson, 2004）。

在这样的背景下，视觉框架逐渐被概念化为一种可以比较、可以编码的分析对象。例如，Rodriguez和Dimitrova（2011）将视觉框架区分为四个层次——指称层、风格—符号层、内涵层与意识形态层——从而推动视觉框架研究从直觉式描述走向更系统的分析路径。

尽管视觉框架相对于文本框架的独特性已得到确认，但当前框架理论研究仍然主要聚焦于静态视觉材料，例如新闻照片与文本之间的关系（Rodriguez & Dimitrova, 2011）。而对于动态视频中具有连续性、时间化与多模态特征的视觉框架，除了少量质性解释性研究外，现有研究仍缺乏系统的识别与测量路径（Fazeli et al., 2023; Geise & Xu, 2025）。目前已有研究开始借助计算方法处理视频中的视觉特征，例如通过色彩与亮度等符号特征识别科学阴谋论视频（Chen et al., 2022），或分析政治人物在辩论视频中展现的非言语元素如何影响选民的即时印象（Bucy & Joo, 2021）。然而，这些研究大多聚焦于局部视觉特征，尚未将视频作为一个具有连续时间序列和整体意义组织的传播单元加以理解，因此仍然缺乏对其内部视觉框架更具结构性的认识（Fazeli et al., 2023; Geise & Xu, 2025）。基于此，本文尝试以中国“吸毒记录封存”议题相关抖音视频为样本，构建一种适用于大规模短视频的自动化视觉框架识别方法，并据此考察该议题中主要存在的视觉框架。

### 多模态框架组合中的一致与冲突

作为一种同时由视觉框架与文本框架构成的多模态媒介形式，短视频为理解框架如何影响评论区中的愤怒表达提供了新的分析材料，同时也提出了更复杂的理论问题。不同于静态多模态媒介，短视频中的视觉与文本并不是彼此独立发挥作用，而是处于持续互动之中。基于模态特征，视觉与文本在传播过程中承担着不同但互补的功能（Kress & van Leeuwen, 2021）。视觉材料通常在吸引注意和唤起情绪方面具有显著优势，其整体性和高信息密度使其能够在极短时间内设定情境与情绪基调。相比之下，文本更擅长提供因果链条与规范性评价，通过线性逻辑推演，将情境信息转化为可归责、可判断的意义。

Powell等人通过实验分别比较了图像框架、文本框架及二者组合的效果，发现当两者分开呈现时，图像往往比文本更能影响受众的态度与行为意向；而当图文共同出现时，受众反应并不只是两种模态效应的简单相加，图像与文本在认知框架上的一致或冲突，会改变整体框架效应（Powell et al., 2015）。他们的研究揭示了一个多模态互动问题，即在真实传播单元中，视觉与文本的意向并不总是一致的。短视频中的框架与叙事表达也并不总是经过理性而完整的安排。这意味着，在短视频这种高度多模态的传播环境中，情绪效应不能仅从文本立场或框架内容本身推出，而应放在视觉与文本如何彼此结合、强化或牵制的关系中加以理解。

近年来的研究又将这一问题推进到更具体的情境中。例如，在气候变化新闻中，图文一致有助于提升新闻显著性；而当图文不一致时，受众往往更可能优先采用图片所暗示的视角（Mosallaei & Feldman, 2024）。在公益传播帖子中，图文情绪不一致，尤其是“负面情绪图片+正面情绪文本”的组合，会显著降低受众参与度（Kwon et al., 2022）；而在餐厅评论中，图文主题一致则会促进信息传递与受众参与（Ceylan et al., 2024）。传统新闻媒体在纸媒报道中同样会考虑视觉框架与文本框架之间的配合，以便利用视觉符号去佐证、甚至放大文本预设的核心立场（Ehmer & Kothari, 2018）。

总体来看，现有研究较为清楚地表明了两点。第一，视觉框架具有独立有效性，不能被降格为文本框架的附属物。第二，在同一传播单元中，视觉与文本既可能保持一致并相互强化，也可能彼此错位、互相竞争，而这会显著影响传播效果。

然而，尽管现有经验研究已经表明视觉材料通常在吸引注意和唤起情绪方面更具主导性，多模态框架研究也表明不同模态的组合会影响责任归因与政策判断，但对于短视频这样一种连续、动态的传播对象，视觉框架与文本框架究竟如何在单个视频内部形成可比的关系结构，以及这些结构是否会进一步关联到评论区中的愤怒表达，仍然缺乏更直接的经验检验。基于此，本文将视觉与文本之间的组合关系视为分析焦点，并提出以下研究问题：

RQ1：在“吸毒记录封存”相关短视频中，主导性视觉框架与主导性文本框架呈现出何种分布特征？

RQ2：在单个短视频中，主导性视觉框架与主导性文本框架会形成何种组合模式？

RQ3：不同的视觉—文本框架组合，与评论区中愤怒表达的强度与分布之间，是否存在显著关联？它们的框架效应是否可以叠加？

## 方法

### 数据来源与样本构建说明

本文选取抖音平台（中国版TikTok）作为案例讨论的数据来源。作为中国用户规模最大的短视频平台之一，抖音在公共议题传播与情绪扩散中发挥着重要作用。本研究考察的案例与《中华人民共和国治安管理处罚法》的修订直接相关。2025年6月，该法修订草案三审稿提出“违反治安管理的记录应当封存”，正式修订后的法律于2026年1月1日生效。2025年11月至12月间，随着媒体集中报道“吸毒记录也纳入封存范围”，这一议题迅速在公共舆论中升温。在中国长期严厉打击毒品的背景下，这一提议引发了公众对公共安全的广泛关切与争议，并进而激发了围绕该话题的激烈讨论。因此，抖音上相关短视频内容及其评论区互动，为考察短视频多模态框架与评论区愤怒表达之间的关系提供了一个合适的经验场域。

本文以中国抖音平台上的相关议题视频及其一级评论文本为研究对象，使用自建的Python爬虫进行数据采集。考虑到公共议题通常会经历一个由迅速升温到关注回落的“议题注意周期”，本文结合该事件在平台上的传播节奏，将数据抓取期设定为2025年11月26日至2026年2月20日（Downs, 1972）。完成初步抓取后，研究又依据关键词相关性、内容完整性与样本可得性对视频进行筛选，剔除了与研究议题无关的样本、重复上传、内容不完整或无法有效获取评论信息的视频。最终获得449条相关短视频和419,126条评论。

### 计算框架分析

本文从两个维度对短视频中的情绪组织进行编码，即叙事文本与视觉模态，并在视频层面形成对应的主导框架变量。需要说明的是，本文在操作化中明确区分“文本模态”与“视觉模态”，画面中的文字内容并不计入视觉模态，而是被单独提取并纳入文本材料包（Fazeli et al., 2023）。这一处理的目的，是为了避免画面中的文字直接干扰视觉编码，从而使视觉框架更多依赖人物、场景、物体、动作、构图与氛围等非文本视觉资源来加以识别。

在叙事框架层面，本文首先转录短视频中的口播、字幕与额外说明，形成视频文本；随后在尽量保留原有语义结构的基础上，对转录文本进行清洗与标准化，并实施编码。结合开放式编码结果与样本特征，本文将文本层面的高阶框架概括为三类：强化框架、信息框架与缓释框架。

其中，强化框架指文本通过风险、防范、不公、纵容、责任追究、代价、社会危害与制度失灵等表述，把议题组织成一个需要警惕、谴责或迅速行动的问题，从而强化紧张感与情绪唤醒。凡是明确突出潜在风险、强调行为者或制度安排责任、使用明显警示性、控诉性或谴责性语言，并推动受众形成负面道德判断的文本，均被归为强化框架。

信息框架是指文本主要承担事件介绍、背景补充、制度说明、规则解释、边界澄清与事实陈述等功能，并不以推动情绪升级或主动降温为目标。凡是主要提供事实、解释政策、说明程序、澄清误解或补充一般性信息，且既不明显强化风险预警、责任归因与道德谴责，也不通过程序化、规范化表达明显压低议题张力的文本，都归入信息框架。

缓释框架则是指文本通过强调制度边界、程序控制、规则约束、专业回应与澄清误解等方式，将议题组织成一个可以依据正式程序被理解和处理的问题，从而降低风险感与情绪张力。凡是明确突出“不是不管”“仍有制度把关”“应当依照法律程序理解”等程序性、规范性表达，并以降温、去风险化或稳定认知为主要取向的文本，均被归为缓释框架。由于样本量有限，文本编码由两位传播学专业学生完成，一致性较好（Cohen’s kappa = 0.85），表明分类结果具有较好的信度。

在视觉框架层面，本文并不以单一静态截图代表整个短视频，而是将视频视为由连续视觉片段构成的动态材料。本文借鉴VisTopics所采用的帧提取、去冗余与语义分析流程，使视觉框架识别建立在连续帧基础上，而非孤立图像之上。该方法在452条NBC News视频中，将11,070帧压缩为6,928张去冗余图像，并进一步识别出35个视觉主题，显示出其在大规模视觉材料分析中的可扩展性（Lokmanoglu & Walter, 2025）。结合本研究对象的特点，视觉框架识别分为如下步骤：

第一，以每秒1帧的固定频率对每条视频进行抽帧，以尽可能保留视频的连续视觉内容及其时间分布；

第二，对相邻抽取帧计算感知哈希值，以识别连续出现的高相似帧，并将这些相似帧归为同一个视觉片段；

第三，在每组相似帧中保留一张代表帧，作为该视觉片段的语义识别对象；

第四，将代表帧输入LLM或图像描述模型，生成结构化视觉描述文本，如人物类型、场景类型、动作关系、情绪表达、符号、镜头距离与整体氛围；

第五，在此基础上，依据预设视觉框架类别清单，对每一张代表帧进行演绎编码，并将编码结果映射回原始视频时间线。程序完整代码已备份于GitHub。（编码示例如表1所示）

不同于文本编码，视觉层面的高阶框架同样被概括为三类：强化框架、信息框架与缓释框架。其中，强化框架主要表现为警示、威慑、异常化、痛苦后果与高压氛围，例如警灯、警戒线、抓捕联想、打码遮脸、阴影人物、毒品器具、悲剧性后果以及强受害场景等。信息框架主要体现为一般信息画面、普通口播、新闻播报、常规采访与说明性镜头，即其主要负责信息传递与背景介绍，但并不明显强化风险感，也不主动承担降温功能。缓释框架则主要表现为法律页面、机构门牌、蓝底回应页面、规范空间中的程序性信息画面与专业解释性场景，它们通过制度化、程序化与有序的视觉资源，传达出该议题仍处于可控处理范围之内的意义。最后，本文计算每条视频中强化、信息与缓释视觉框架的时长占比，并以占比最高者识别主导视觉框架。

### 多模态关系变量

在完成文本与视觉编码之后，本文进一步在视频层面构建二者之间的关系变量。首先，比较主导文本框架与主导视觉框架是否一致，据此形成一致、不一致与部分一致三种组合类型。同时，本文也保留了视觉框架与文本框架的具体组合变量，用于识别不同类型的多模态搭配。后续统计分析将利用这些关系变量，检验多模态结构与评论区愤怒表达之间的关联。

### 愤怒测量方法

本文将“愤怒表达”界定为评论者对某一行为者或制度安排所表现出的明显不满、谴责、斥责或怨恨，以及对被感知到的规范违背所作出的道德性回应（Leach et al., 2025）。仅表达无助、悲伤、失望、恐惧或嘲讽等其他负面情绪的评论，或者只是包含负面评价但并未形成清晰愤怒指向的评论，均不纳入愤怒表达类别。该定义借鉴了社交媒体文本中愤怒表达操作化研究的既有思路（Monge & Laurent, 2024）。

在具体编码过程中，本文首先从全部评论数据中抽取10,000条评论样本，构建人工标注集，并依据编码手册逐条判定。编码手册明确规定，凡出现“furious”“angry”“outrageous”等愤怒词汇，出现“How dare you?”“That’s disgusting”等带有强烈斥责意味的表达，或通过连续问号、感叹号、表情符号等辅助符号强化愤怒语气的文本，均被判定为愤怒表达。人工标注由两位编码员独立完成，正式标注前接受了训练与预试。两位编码员在随机抽取的10,000条预标注样本上的Cohen’s Kappa系数为0.87，一致性极高；对于存在分歧的条目，则通过讨论达成一致。

为了在全样本数据中识别愤怒表达强度，本文使用基于双向Transformer结构的语言预训练模型BERT，对评论区文本进行二元分类，并基于内容分析结果对预训练BERT模型进行微调，以构建最优模型。

基于标注集训练得到的BERT模型参数如表2所示，其中，Validation_split表示验证集在整体数据集中的占比，Batch_size反映样本数据的整体特征，Epochs表示模型训练的迭代轮数，Learning_rate则是决定模型收敛速度的学习率。优化过程中使用Adam优化器。根据情绪分类任务结果，模型的精准率与召回率均接近理想状态，因此可认为该情绪分类模型具有较高准确性（见表2）。

## 结果

### 样本与变量描述

在样本规模层面，本研究共纳入449条相关视频，对应419,126条一级评论，平均每条视频拥有895.57条有效评论，表明该议题在平台上具有较高的互动强度与可见性。经机器学习模型识别后，共检出48,973条愤怒评论，约占全部一级评论的11.68%。视频层面的愤怒率均值为0.099，中位数为0.087。

总体而言，大约10%的一级评论表现出清晰的愤怒表达，但不同视频之间的愤怒水平存在显著波动。

在因变量设定上，本文以单条短视频为分析单位，将评论层面的愤怒识别结果聚合为视频层面的愤怒率指标，并将其作为核心因变量。在解释变量设定上，本文构建了两个核心变量：主导视觉框架与主导文本框架。视觉框架依据视频中不同视觉内容的时间占比确定，分为强化型、信息型与缓释型，样本量分别为68条（15.1%）、189条（42.1%）与192条（42.8%）。文本框架则依据口播、字幕与额外说明编码，同样被划分为强化型、信息型与缓释型，样本量分别为78条（17.4%）、111条（24.7%）与260条（57.9%）。总体来看，无论在视觉维度还是文本维度，样本都以信息框架和缓释框架为主，而强化框架所占比例相对较低。（结果见图1）

### 不同组合模式下的愤怒表达差异

虽然列联表显示视觉框架与文本框架经常成对出现，表现出更多一致而较少冲突，但不同框架组合是否对应不同水平的愤怒，仍然未知。为检验不同视觉—文本框架组合是否对应评论区中不同水平的愤怒表达，本文采用Kruskal–Wallis检验，对九种组合之间的组间差异进行比较。结果显示，视频层面的愤怒率在不同组合之间存在显著差异，χ²(8) = 50.98, p < .001。

描述性统计进一步表明，愤怒率呈现出清晰的层级分化。当视觉与文本都偏向缓释时，愤怒率最低（M = 0.064），其中位数仅为0.035，显著低于其他组合。虽然当视觉与文本都偏向强化时，愤怒率也相对较高（M = 0.142），但它仍略低于“信息型视觉框架 + 强化型文本框架”的组合。

如下图所示，文本强化似乎与更高的愤怒表达更为直接相关。无论视觉框架是信息型还是强化型，只要文本框架进入强化类别，愤怒率都会维持在较高水平。这表明，文本对风险与责任的强调，可能比单纯的视觉刺激更直接地推动愤怒表达。相比之下，“双重缓释”组合显示出最明显的降温效应：当视觉与文本同时采取缓释框架时，评论区愤怒率显著更低。通过中位数检验，这一趋势甚至更加稳健。

总之，不同视觉与文本框架组合与评论区中的愤怒表达之间存在显著关联，而且这种关联呈现出明确的方向性模式：包含强化型视觉与强化型文本的组合，更可能对应较高水平的愤怒；而在视觉与文本都偏向缓释的组合中，愤怒率则显著较低。（结果见图2）

### 双因素方差分析

在确认不同视觉—文本组合对应显著不同的愤怒率之后，本文进一步考察，这种差异究竟来自特定组合本身，还是来自视觉框架与文本框架各自主效应的叠加。为此，本文以视频层面的愤怒率为因变量，以主导视觉框架、主导文本框架及二者交互项为预测变量，实施双因素方差分析。

结果显示，视觉框架的主效应显著，F(2, 440) = 17.74, p < .001；文本框架的主效应也显著，F(2, 440) = 5.51, p = .004；而二者之间的交互作用并不显著，F(4, 440) = 0.28, p = .893。如图4所示，愤怒率在不同视觉框架之间、也在不同文本框架之间存在显著差异，但视觉框架与文本框架并未形成稳定的交互增强机制。换言之，尽管九种组合在描述统计上呈现出清晰的高低分化，但这种格局并不意味着某些特定组合会产生超出两种模态效应之和的特殊效果。

为进一步验证这一解释，本文又估计了一个不包含交互项的主效应模型。结果表明，视觉框架的主效应依然显著，F(2, 444) = 13.89, p < .001；文本框架的主效应同样显著，F(2, 444) = 5.54, p = .004。这说明，视觉框架与文本框架对愤怒表达的影响并不依赖于交互项，而是作为相对独立的因素稳定发挥作用。结合前文的描述性统计可以看出，视觉与文本中的强化或缓释倾向会分别、独立地改变愤怒率，而组合之间的差异，主要是这两种效应在视频层面的叠加结果。从解释上说，视觉模态与文本模态都会独立影响评论区中的愤怒表达，但这种影响并未表现出显著的交互放大，而更接近线性叠加。（结果见图3）

### 稳健性检验

为检验上述发现的稳健性，本文开展了两组补充分析。首先，由于视频层面的愤怒率是一个取值范围在0到1之间的比例变量，本文在基准OLS模型之外，进一步采用分数对数几率模型（fractional logit），重新估计视觉框架、文本框架、交互项与愤怒率之间的关系。其次，本文将点赞数、粉丝量与发布时间等平台情境变量纳入基准线性模型，以检验在控制账号属性与传播时点之后，视觉框架与文本框架的效应是否仍然存在。

分数对数几率模型给出的不同视觉—文本组合之预测愤怒率排序，与基准OLS模型大体一致。其中，“信息型视觉—强化型文本”组合的预测愤怒率最高，为0.145，95% CI [0.111, 0.186]；“强化型视觉—强化型文本”组合位列第二，为0.142，95% CI [0.110, 0.180]；而“缓释型视觉—缓释型文本”组合最低，为0.064，95% CI [0.053, 0.077]。其余组合的预测值介于0.099到0.128之间。该结果表明，本文的核心结论——即包含强化型文本的组合通常对应更高的愤怒率，而“双重缓释”组合对应最低的愤怒率——在采用更适合比例型因变量的模型之后，并未发生实质性变化。

## 讨论

本研究以中国“吸毒记录封存”议题相关抖音短视频为案例，结合计算框架分析与评论区愤怒识别，考察了短视频中视觉框架与文本框架的组合方式，以及这种多模态结构与评论区愤怒表达之间的关系。基于前述数据分析结果，本文得到三项发现。第一，视觉框架与文本框架之间并非随机并置，而是呈现出显著的同向关联，这表明短视频中的多模态意义生产更可能表现为协调性组织，而不是彼此脱节。第二，不同的视觉与文本框架组合，确实对应评论区中不同水平的愤怒率，这种组合对于评论区愤怒的激发具有一定影响。第三，视觉框架与文本框架对愤怒表达的作用，主要体现为各自主效应的平行累积，而不是显著的统计交互效应。

在方法层面，上述方法有助于推进动态短视频情境下的多模态框架研究。尽管仅使用时长占比最高的主导框架作为分析材料，未必能够充分捕捉一个视频在情绪层面的全部视觉特征；也尽管视频中某个关键帧有时可能比其他所有画面加总起来更能激发愤怒，但我认为，这一方法对于视觉框架研究仍然具有帮助，尤其适合探索大规模数据中的模态间关系，并且随着人工智能工具逐渐变得更加可靠，它可能会展现出更大效用（Peng et al., 2024; Fazeli et al., 2023; Lokmanoglu & Walter, 2025）。

在理论层面，通过回答RQ1和RQ2，本文发现，在同一事件之中，视觉框架与文本框架的情绪倾向既可以彼此独立，又会同时对受众产生影响，而它们通常会被组织成一个指向一致的整体（Powell et al., 2015; Geise & Xu, 2025）。这意味着，短视频中的多模态结构并不是附着在内容外部的一种修辞装置，它本身就是意义生产的一部分。

本研究还将框架效应的讨论，从认知判断拓展到了外显情绪表达层面。Kühne与Schemer的研究表明，不同新闻框架能够诱发不同的离散情绪，而强化型框架会提高与惩罚有关信息的可得性，并增强受众对惩罚性措施的偏好（Kühne & Schemer, 2015）。本文的结果与这一思路相呼应，并将其进一步拓展到平台评论区这一公开、互动且可观察的情绪场域。Powell等人的实验研究发现，当图像与文本分开呈现时，图像产生的框架效应强于文本；而当图像与文本共同出现时，一致与冲突会改变整体效应（Powell et al., 2015）。本文结果总体上也与这一判断相一致。不过，就当前发现而言，更谨慎的解释并不是“文本必然比视觉更重要”，而是：文本中的强化性叙事更接近于直接明确地表达道德谴责与惩罚想象，因此更容易直接转化为评论区中的外显愤怒；相比之下，视觉模态更接近于事前设定情境、威胁感与情绪基调。也正因如此，二者在统计上表现为主效应的平行累积，而非稳定的交互增强机制。这进一步表明，在短视频中，情绪并不是被单一模态瞬间触发的，而是在视觉与文本共同进行责任归因的过程中，被逐步组织起来的。

这一发现也有助于我们更好理解平台上的愤怒表达。强化型文本框架之所以更可能对应较高愤怒率，恰恰在于它通常利用风险、预防、失守、纵容、牺牲与责任追究等叙事资源，把议题组织成一个需要迅速作出道德判断的问题。相较之下，缓释框架则通过强调制度边界、程序可控性与规则仍在运行，降低了受众对于失控、纵容与不公的感知，从而压缩了愤怒表达释放的空间。换言之，短视频评论区中的愤怒，并不只是议题争议性的自然外溢，它也是内容如何组织责任归因与可控性的结果。

最后，本文仍有若干局限需要说明。第一，评论区中的愤怒表达只是可见的外显情绪，而不是受众全部内部情绪状态，本文无法直接观察那些沉默观看者对视频内容的感受。第二，本文聚焦于单一议题和特定时间窗口，因此当前结论更适合作为一个关于高度争议性治理议题的经验发现，而不是适用于所有公共议题的一般规律。同时，由于中国审查制度的限制，本研究的数据收集也受到相当大的约束（King et al., 2013）。最后，本文揭示的是多模态框架与愤怒表达之间的系统性关联，而非严格意义上的强因果识别。未来研究可以进一步扩展到不同议题、不同平台与不同文化情境，并结合实验设计、纵向追踪或更细粒度的互动数据，继续检验视觉与文本如何在平台环境中共同塑造情绪表达。

## 参考文献

参考文献保留原文如下：

Arora, A., Yadav, S., Antoniak, M., Belongie, S., & Augenstein, I. (2025, November). Multi-modal framing analysis of news. In Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing (pp. 31519–31541).

Bucy, E. P., & Joo, J. (2021). Editors’ introduction: Visual politics, grand collaborative programs, and the opportunity to think big. The International Journal of Press/Politics, 26(1), 5–21. https://doi.org/10.1177/1940161220970361

Ceylan, G., Diehl, K., & Proserpio, D. (2024). Words meet photos: When and why photos increase review helpfulness. Journal of Marketing Research, 61(1), 5–26. https://doi.org/10.1177/00222437231169711

Chen, K., Kim, S. J., Gao, Q., & Raschka, S. (2022). Visual framing of science conspiracy videos: Integrating machine learning with communication theories to study the use of color and brightness. Computational Communication Research, 4(1). https://doi.org/10.5117/CCR2022.1.003.CHEN

Chen, V. Y. (2025). Coexistence of value construction and value destruction: The effect of social media news engagement and emotional news on news paying intent. Journalism, 26(1), 187–206. https://doi.org/10.1177/14648849241229261

Coleman, R. (2010). Framing the pictures in our heads. In P. D’Angelo & J. A. Kuypers (Eds.), Doing news framing analysis: Empirical and theoretical perspectives (pp. 233–261). Routledge.

Dan, V. (2017). Integrative framing analysis: Framing health through words and visuals. Routledge.

Dawtry, R. J., Callan, M. J., Harvey, A. J., & Gheorghiu, A. I. (2020). Victims, vignettes, and videos: Meta-analytic and experimental evidence that emotional impact enhances the derogation of innocent victims. Personality and Social Psychology Review, 24(3), 233–259.

Dimitrova, D. V., Bock, M. A., Bucy, E. P., Coleman, R., & Dan, V. (2025). The power of visual framing in the age of AI. Journalism & Mass Communication Quarterly. Advance online publication. https://doi.org/10.1177/10776990251392597

Downs, A. (2016). Up and down with ecology: The “issue-attention cycle.” In Agenda setting (pp. 27–33). Routledge.

Eberl, J. M., Tolochko, P., Jost, P., Heidenreich, T., & Boomgaarden, H. G. (2020). What’s in a post? How sentiment and issue salience affect users’ emotional reactions on Facebook. Journal of Information Technology & Politics, 17(1), 48–65.

Ehmer, E. A., & Kothari, A. (2018). Coverage of Burmese refugees in Indiana news media: An analysis of textual and visual frames. Journalism, 19(11), 1552–1569.

Ekström, M., & Shehata, A. (2024). Amplified news framing of social disturbance and its impact on authoritarian attitudes: An experimental study of main effects and activation of predispositions. Journalism & Mass Communication Quarterly. Advance online publication.

Entman, R. M. (1993). Framing: Toward clarification of a fractured paradigm. Journal of Communication, 43, 51–58.

Fazeli, S., Sabetti, J., & Ferrari, M. (2023). Performing qualitative content analysis of video data in social sciences and medicine: The visual-verbal video analysis method. International Journal of Qualitative Methods, 22, 16094069231185452.

Geise, S., & Xu, Y. (2025). Effects of visual framing in multimodal media environments: A systematic review of studies between 1979 and 2023. Journalism & Mass Communication Quarterly, 102(3), 796–823. https://doi.org/10.1177/1077699024125758

Goffman, E. (1974). Frame analysis: An essay on the organization of experience. Northeastern University Press.

Hasell, A., Halversen, A., & Weeks, B. E. (2025). When social media attack: How exposure to political attacks on social media promotes anger and political cynicism. The International Journal of Press/Politics, 30(1), 167–186.

Humprecht, E., Hellmueller, L., & Lischka, J. A. (2020). Hostile emotions in news comments: A cross-national analysis of Facebook discussions. Social Media + Society, 6(1), 2056305120912481.

Iyer, A., & Oldmeadow, J. (2006). Picture this: Emotional and political responses to photographs of the Kenneth Bigley kidnapping. European Journal of Social Psychology, 36(5), 635–647.

Kress, G., & Van Leeuwen, T. (2020). Reading images: The grammar of visual design. Routledge.

Kühne, R., & Schemer, C. (2015). The emotional effects of news frames on information processing and opinion formation. Communication Research, 42(3), 387–407.

Kühne, R., Schemer, C., Matthes, J., & Wirth, W. (2011). Affective priming in political campaigns: How campaign-induced emotions prime political opinions. International Journal of Public Opinion Research, 23(4), 485–507. https://doi.org/10.1093/ijpor/edr004

Kühne, R., Weber, P., & Sommer, K. (2015). Beyond cognitive framing processes: Anger mediates the effects of responsibility framing on the preference for punitive measures. Journal of Communication, 65(2), 259–279.

Kwon, J., Lin, H., Deng, L., Dellicompagni, T., & Kang, M. Y. (2022). Computerized emotional content analysis: Empirical findings based on charity social media advertisements. International Journal of Advertising, 41(7), 1314–1337.

Leach, S., Formanowicz, M., Nikadon, J., & Cichocka, A. (2026). Moral outrage predicts the virality of petitions for change on social media, but not the number of signatures they receive. Social Psychological and Personality Science, 17(2), 194–203.

Lee, J., & Britt, B. C. (2024). Factbait: Emotionality of fact-checking tweets and users’ engagement during the 2020 US presidential election and the COVID-19 pandemic. Digital Journalism, 12(10), 1523–1547.

Liang, M., & Ye, L. (2025). Algorithmic pedagogy: How Douyin constructs algorithmic imaginaries for content creators. Platforms & Society, 2. https://doi.org/10.1177/29768624251365615

Lokmanoglu, A. D., & Walter, D. (2025). Topic modeling of video and image data: A visual semantic unsupervised approach. Communication Methods and Measures, 19(3), 232–279. https://doi.org/10.1080/19312458.2025.2549707

Mendelson, A. L. (2004). For whom is a picture worth a thousand words? Effects of the visualizing cognitive style and attention on processing of news photos. Journal of Visual Literacy, 24(1), 1–22.

Messaris, P. (2003). Visual communication: Theory and research. Journal of Communication, 53(3), 551–556.

Mitchell, W. J. T. (1994). Picture theory: Essays on verbal and visual representation. University of Chicago Press.

Monge, C. K., & Laurent, S. M. (2024). Signaling outrage is a signal about the sender: Moral perceptions of online flaming. Journal of Computer-Mediated Communication, 29(2), zmae001.

Montada, L., & Schneider, A. (1989). Justice and emotional reactions to the disadvantaged. Social Justice Research, 3(4), 313–344.

Mosallaei, A., & Feldman, L. (2024). Do you see what I see? Perceptions and effects of image–text congruency in online climate change news. Journalism & Mass Communication Quarterly. Advance online publication. https://doi.org/10.1177/10776990241284596

Nabi, R. L. (2003). Exploring the framing effects of emotion: Do discrete emotions differentially influence information accessibility, information seeking, and policy preference? Communication Research, 30(2), 224–247.

O’Brien, H. L., Davoudi, N., & Nelson, M. (2025). TikTok as information space: A scoping review of information behavior on TikTok. Library & Information Science Research, 47(4), Article 101379. https://doi.org/10.1016/j.lisr.2025.101379

Peng, Y., Lock, I., & Ali Salah, A. (2024). Automated visual analysis for the study of social media effects: Opportunities, approaches, and challenges. Communication Methods and Measures, 18(2), 163–185.

Powell, T. E., Boomgaarden, H. G., De Swert, K., & De Vreese, C. H. (2015). A clearer picture: The contribution of visuals and text to framing effects. Journal of Communication, 65(6), 997–1017.

Rico, G., Guinjoan, M., & Anduiza, E. (2017). The emotional underpinnings of populism: How anger and fear affect populist attitudes. Swiss Political Science Review, 23(4), 444–461.

Rodriguez, L., & Dimitrova, D. V. (2011). The levels of visual framing. Journal of Visual Literacy, 30(1), 48–65.

Sun, N., Rau, P. P. L., & Ma, L. (2014). Understanding lurkers in online communities: A literature review. Computers in Human Behavior, 38, 110–117.

Valenzuela, S., Piña, M., & Ramírez, J. (2017). Behavioral effects of framing on social media users: How conflict, economic, human interest, and morality frames drive news sharing. Journal of Communication, 67(5), 803–826.

Van Dijck, J., Poell, T., & De Waal, M. (2018). The platform society: Public values in a connective world. Oxford University Press.

Van Zomeren, M., Spears, R., Fischer, A. H., & Leach, C. W. (2004). Put your money where your mouth is! Explaining collective action tendencies through group-based anger and group efficacy. Journal of Personality and Social Psychology, 87(5), 649–664.

Wayne, C. N. (2023). Terrified or enraged? Emotional microfoundations of public counterterror attitudes. International Organization, 77(4), 824–847.

Weaver, D. A., Lively, E., & Bimber, B. (2009). Searching for a frame: News media tell the story of technological progress, risk, and regulation. Science Communication, 31(2), 139–166.

Xu, Y. (2025). The multimodal turn in framing paradigm: A systematic review of visual framing publications during 1979–2023. Annals of the International Communication Association, 49(2), 96–107.

Yu, Z., Hou, J., & Zhou, O. T. (2023). Short video activism with and on Douyin: An innovative repertoire of contention for Chinese consumers. Social Media + Society, 9(1), 20563051231157603.

Zhang, X., & Fu, X. (2022). Fact-checkers’ usage of clickbait element on social media and its effects on user engagement. Global Journal of Media Studies, 9(3), 7.

## 表格与图注翻译

### 表3 视频层面愤怒率的双因素方差分析结果

列名翻译：
- Effect：效应
- SS：平方和
- df：自由度
- MS：均方
- F：F值
- P：显著性
- Partial η²：偏η²

注：N = 449。该表报告了完整双因素方差分析模型的结果，包括视觉框架与文本框架的主效应，以及二者的交互项。偏η²表示效应量。

### 表1 视觉编码示例

- Intensifying frame：强化框架
  - coding indicators：编码指标
  - 强调威胁、惩罚、痛苦或道德紧迫性的图像，例如警灯、手铐、遮脸处理、阴暗或紧张场景、与毒品有关的物品，以及其他带有警示取向的视觉元素。
  - Examples：示例

- Informational frame：信息框架
  - coding indicators：编码指标
  - 主要提供事实背景或议题解释的图像，例如普通出镜口播、新闻播报、常规采访，以及没有明显情绪强化或降温倾向的一般性说明画面。
  - Examples：示例

- Mitigating frame：缓释框架
  - coding indicators：编码指标
  - 强调规则、秩序与制度控制的图像，例如法律文件、官方回应页面、机构标识、程序图示，以及暗示该议题仍处于可治理、可控边界内的专业说明性场景。
  - Examples：示例

### 表2 BERT情感分类模型的训练参数与分类表现

### 图1 主导文本框架与视觉框架的分布

注：柱形表示449条视频中主导文本框架与主导视觉框架的百分比分布。柱顶数字表示频数与百分比。浅灰色柱代表文本框架，深灰色柱代表视觉框架。

### 图2 视觉—文本框架组合分布

注：单元格报告频数及行百分比。颜色深浅表示卡方检验中的标准化残差，颜色越深表示该组合出现频率高于期望值，颜色越浅表示该组合出现频率低于期望值。χ² = 50.171, df = 4, p < .001, Cramér’s V = 0.236。

### 图3 不同视觉—文本框架组合下的平均愤怒率

注：单元格报告各视觉—文本框架组合的平均愤怒率与样本量。颜色越深表示平均愤怒率越高。Kruskal–Wallis检验：χ² = 50.984, df = 8, p < .001。
