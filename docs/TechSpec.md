# LingAI（小语灵）技术实现文档

> 版本：POC v0.2  
> 更新：2026-02-09
> 范围：TOPIK I / TOPIK II / 常考单词 闭环验证

---

## 1. 系统架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        鸿蒙 App (ArkTS/ArkUI)               │
├─────────────────────────────────────────────────────────────┤
│  UI Layer    │ 学习Tab │ 词典Tab │ 我的Tab │                │
├──────────────┴─────────┴─────────┴─────────┴────────────────┤
│  Service     │ LessonService │ DictService │ ReviewService │
├──────────────┴──────────────┴─────────────┴─────────────────┤
│  Data        │ RDB (SQLite) │ Preferences │ FileSystem     │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Backend (Python FastAPI)                  │
├─────────────────────────────────────────────────────────────┤
│  /api/tts      │ /api/dict/ai  │ /api/content │ /api/stats │
├────────────────┴───────────────┴──────────────┴─────────────┤
│  阿里云 TTS    │ Deepseek API  │ 通义千问(备用)            │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 技术选型汇总

| 模块 | 技术 | 版本 |
|------|------|------|
| App 框架 | ArkTS / ArkUI | HarmonyOS NEXT |
| App 存储 | RDB + Preferences + FileSystem | - |
| 服务端 | Python + FastAPI + uvicorn | 3.11+ |
| 数据库 | SQLite (本地) | - |
| TTS | 阿里云智能语音 | - |
| LLM 主力 | Deepseek Chat | - |
| LLM 备用 | 阿里云通义千问 | - |

### 1.3 部署架构

**POC 阶段（本地开发）**
```
MBP M2 Max ─┬─ App: DevEco Studio 模拟器/真机
            └─ Server: uvicorn (localhost:8000)
```

**后续生产**
```
阿里云 ECS ─── Docker ─── FastAPI App
```

---

## 2. App 端技术方案

### 2.1 项目结构

```
LingAI/
├── entry/src/main/
│   ├── ets/
│   │   ├── pages/              # 页面
│   │   │   ├── Index.ets       # 首页（Tab容器）
│   │   │   ├── LessonPage.ets  # 关卡学习页
│   │   │   ├── DictPage.ets    # 词典页
│   │   │   └── MinePage.ets    # 我的页
│   │   ├── components/         # 通用组件
│   │   │   ├── FlashCard.ets   # 预习闪卡
│   │   │   ├── QuizCard.ets    # 练习题卡
│   │   │   ├── WordCard.ets    # 词条卡片
│   │   │   ├── DictContent.ets # 词典内容组件(支持嵌入)
│   │   │   └── VocabularyContent.ets # 生词本内容组件
│   │   ├── services/           # 业务服务
│   │   │   ├── LessonService.ets
│   │   │   ├── DictService.ets
│   │   │   ├── ReviewService.ets
│   │   │   └── SyncService.ets
│   │   ├── models/             # 数据模型
│   │   ├── utils/              # 工具类
│   │   └── constants/          # 常量定义
│   └── resources/              # 资源文件
└── oh-package.json5
```

### 2.2 本地存储设计

#### Preferences（键值存储）
```typescript
// 用户设置
interface UserSettings {
  notificationEnabled: boolean;      // 通知开关（默认false）
  notificationTime: string;          // 提醒时间（默认"09:00"）
  autoDownloadCount: number;         // 自动下载关卡数（默认3）
}

// 学习状态
interface LearningState {
  currentLevel: number;              // 当前等级（1-6）
  currentLesson: number;             // 当前关卡
  lastOpenTime: number;              // 最后打开时间
}
```

#### RDB（关系型数据库）
```sql
-- 词条表
CREATE TABLE word_entry (
  id INTEGER PRIMARY KEY,
  hangul TEXT NOT NULL,              -- 韩文
  romanization TEXT,                 -- 罗马音
  pos TEXT,                          -- 词性
  primary_meaning TEXT NOT NULL,     -- 主释义
  senses TEXT,                       -- 多义项(JSON)
  collocations TEXT,                 -- 搭配(JSON)
  examples TEXT,                     -- 例句(JSON)
  topik_level INTEGER NOT NULL,      -- TOPIK等级
  freq_rank INTEGER,                 -- 词频排序
  lesson_id INTEGER NOT NULL         -- 所属关卡
);

-- 学习进度表
CREATE TABLE lesson_progress (
  lesson_id INTEGER PRIMARY KEY,
  level INTEGER NOT NULL,            -- 所属等级
  status INTEGER DEFAULT 0,          -- 0:锁定 1:进行中 2:已通关
  mastered_count INTEGER DEFAULT 0,  -- 已掌握词数
  mastered_words TEXT,               -- 已掌握词ID(JSON)
  skipped_words TEXT,                -- 已跳过词ID(JSON)
  correct_counts TEXT,               -- 各词答对次数(JSON)
  updated_at INTEGER
);

-- 生词本表
CREATE TABLE wordbook (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  word_id INTEGER NOT NULL,
  source TEXT DEFAULT 'dictionary',  -- 来源
  created_at INTEGER NOT NULL,
  next_review_at INTEGER,            -- 下次复习时间
  review_stage INTEGER DEFAULT 0,    -- 复习阶段(0-5对应D0-D30)
  ai_mnemonic TEXT,                  -- AI联想记忆(缓存)
  FOREIGN KEY (word_id) REFERENCES word_entry(id)
);

-- 每日任务表
CREATE TABLE daily_task (
  date TEXT PRIMARY KEY,             -- 日期 YYYY-MM-DD
  lesson_step_done INTEGER DEFAULT 0,
  review_count INTEGER DEFAULT 0,
  study_minutes INTEGER DEFAULT 0,
  updated_at INTEGER
);

-- 统计事件表
CREATE TABLE stat_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_name TEXT NOT NULL,
  event_data TEXT,                   -- JSON
  created_at INTEGER NOT NULL
);
```

#### 每日任务系统 (TaskTrackingService)

**核心方法**:
```typescript
class TaskTrackingService {
  recordLessonStep(): Promise<void>              // 记录关卡步骤完成（累加）
  recordReviewComplete(count: number): Promise<void>  // 记录复习完成
  startStudyTimer(): void                        // 开始学习计时
  pauseStudyTimer(): void                        // 暂停学习计时
  getCurrentTask(): DailyTask                    // 获取当前任务
  refreshTask(): Promise<DailyTask>              // 刷新任务数据
  setOnUpdateCallback(callback): void            // UI更新回调
}
```

**任务进度触发点**:
- **T1 推进1关** - LessonPage 完成预习或练习回调 `recordLessonStep()`，累加计数
- **T2 复习20词** - VocabularyService.markReviewed() 回调 `recordReviewComplete(1)`
- **T3 学习10分** - LessonPage onPageShow/onPageHide 控制计时器

**UI实时刷新机制**:
- 使用 `taskVersionKey` + `ForEach` 强制组件重建
- TaskTrackingService 通过回调直接更新父组件状态：
  ```typescript
  this.taskService.setOnUpdateCallback((task: DailyTask) => {
    this.dailyTask = task;
    this.taskVersionKey++; // 触发ForEach重建
  });
  ```

**任务显示逻辑**:
- **进度条**: 达到目标后封顶100%
- **数值显示**: 显示实际累计值（可超过目标）
- 例：推进3关 → 进度条100% (1/1)，显示"3"

**数据持久化**:
- 本地 RDB daily_task 表按日期存储
- 跨日自动创建新记录重置进度

### 设置页面 (SettingsContent)

**UI组件**:
- Sheet 面板形式展示 (80% 高度)
- 每关单词数滑块 (10-50，步长10)
- 关卡数实时预览表格

**数据流**:
```typescript
// 读取设置
preferences.get('wordsPerLesson', 20)

// 保存设置
preferences.put('wordsPerLesson', value)
preferences.flush()

// 动态计算
lessonCount = Math.ceil(wordCount / wordsPerLesson)
```

**各等级词汇总数**:
- TOPIK I: 1559词
- TOPIK II: 3764词
- 常考单词: 1203词

**刷新机制**:
- Index.ets 切换到学习Tab时调用 `reloadSettingsAndRefresh()`
- 重新读取 preferences 并更新 `lessonList`
- LessonPage 启动时读取 wordsPerLesson 传给 API

---

### 学习统计页面 (StatisticsPage)

**UI组件**:
- 标题栏 + 返回按钮
- 4个卡片模块（List + ListItem）:
  1. 学习概览卡片（4个指标网格）
  2. 今日任务进度（3个进度条）
  3. 学习打卡日历（6×5网格热力图）
  4. 生词本统计（2个数值卡片）

**日历打卡实现**:
```typescript
// 日历日期数据结构
class CalendarDay {
  date: string;          // YYYY-MM-DD
  dayOfMonth: number;    // 日期数字
  studyMinutes: number;  // 学习时长
}

// 热力图颜色映射
getCheckInColor(minutes: number): string {
  if (minutes === 0) return COLORS.BORDER;      // 缺席-灰色
  if (minutes < 15) return '#D1E7DD';           // 浅绿
  if (minutes < 30) return '#A3CFBB';           // 中绿
  if (minutes < 45) return '#75B798';           // 深绿
  return '#4A9F76';                              // 最深绿
}

// 构建30天日历
buildCalendar(): CalendarDay[][] {
  // 生成最近30天日期
  // 从数据库查询匹配的学习记录
  // 按6×5网格排列返回
}
```

**数据模型** (DataModels.ets):
```typescript
// 学习概览统计
class LearningOverview {
  studyDays: number;          // 学习天数
  totalMinutes: number;       // 总学习时长
  lessonsCompleted: number;   // 完成关卡数
  wordsReviewed: number;      // 复习单词数
}

// 每日统计数据
class DailyStats {
  date: string;               // 日期 YYYY-MM-DD
  studyMinutes: number;       // 学习时长
  lessonsCompleted: number;   // 完成关卡数
  reviewCount: number;        // 复习单词数
}

// 生词本统计
class VocabStats {
  reviewPending: number;      // 待复习单词数
  totalWords: number;         // 全部生词数
}
```

**服务层** (StatisticsService.ets):
```typescript
class StatisticsService {
  // 获取学习概览（聚合所有daily_task记录）
  async getOverview(): Promise<LearningOverview>
  
  // 获取最近30日数据（用于日历打卡）
  async getMonthlyTrend(): Promise<DailyStats[]>
  
  // 获取生词本统计（从VocabularyService）
  async getVocabularyStats(): Promise<VocabStats>
}
```

**数据来源**:
- `DatabaseService.getAllDailyTasks()`: 所有学习记录
- `DatabaseService.getRecentDailyTasks(30)`: 最近30天记录
- `VocabularyService.getAllWords()`: 生词本数据
- `TaskTrackingService.getCurrentTask()`: 今日任务

**导航**:
- 入口: Index.ets "我的" Tab → "学习统计" ListItem
- 路由: `router.pushUrl({ url: 'pages/StatisticsPage' })`
- 返回: `router.back()`




#### 文件系统
```
/data/app/lingai/
├── audio_cache/          # TTS音频缓存
│   └── {word_id}.mp3
├── lesson_packs/         # 下载关卡包
│   └── lesson_{id}.json
└── backups/              # 备份文件
    └── backup_{timestamp}.lingai-backup
```

### 2.3 核心页面流程

#### 学习 Tab 流程
```
等级列表 ──▶ 等级详情页(关卡列表) ──▶ 关卡学习页
                     │                      │
                     │                      ├──▶ 预习闪卡(50词)
                     │                      │        │
                     │                      │        ▼ 可跳过
                     │                      ├──▶ 练习(自由刷题)
                     │                      │        │
                     │                      │        ▼ 85%掌握
                     │                      └──▶ 通关结算
                     │
                     └──▶ 加练清单入口

#### 练习阶段交互（QuizCard）
**确认步骤**：
1. 用户点击选项 → 高亮选中，其他选项仍可点击（可重新选择）
2. 底部显示"确认"按钮（未选择时显示灰色+提示）
3. 点击"确认" → 锁定选项、判断对错、显示结果
4. **正确答案**：自动进入下一题（无需手动操作）
5. **错误答案**：显示正确答案 + 解释，需点击"继续"按钮

※优化流程：正确答案快速推进，错误答案强制查看反馈


#### 关卡页小语灵助手（SpiritChatPanel）
**集成方式**：
- 根布局使用 `Stack({ alignContent: Alignment.BottomEnd })`
- `FloatingSpirit` 悬浮按钮位于右下角（margin: right 20, bottom 32）
- 点击展开 `SpiritChatPanel`

**上下文感知**：
- `getSpiritContext()` 生成当前学习内容
- 发送消息时自动注入上下文（用户不可见）

#### FlashCard 预习阶段增强
**生词收录切换**：
- 卡片背面显示"收录生词"/"取消收录"按钮
- 点击"收录生词" → 添加到生词本，按钮变为"取消收录"
- 点击"取消收录" → 从生词本移除，按钮变回"收录生词"
- 返回页面时自动刷新状态（`onPageShow` + `forceReload`）

**内容淡入淡出动画**：
- 切换单词时仅内容区域（单词+释义）参与动画
- 喇叭按钮固定尺寸（56x56），仅改变颜色
- 导航按钮（上一个/下一个）位置固定不参与动画
- 使用 `animateTo` + `contentOpacity` 状态控制

#### 闯关过程中的划词搜索
**场景**：用户在预习闪卡（FlashCard）中遇到生词或想查例句中的词。

**技术实现**：
1. **文本选择**：
   - 启用 `Text.copyOption(CopyOptions.LocalDevice)`。
   - 使用 `onTextSelectionChange` 监听并保存选区内容到组件状态 `selectedText`。
   - 绑定 `bindSelectionMenu`，添加 "🔍 查词" 菜单项。
   - 点击查词时，优先使用 `selectedText`，若为空则降级查询当前主单词。

2. **结果展示**：
   - 在 `LessonPage` 根容器使用 `bindSheet` (半模态)。
   - 复用 `DictContent` 组件，设置 `embedMode=true` (隐藏Header，自动搜索)。
   - 调用 `openDictionary(query)` 更新查询词并展开 Sheet。

#### 词典 Tab 流程
```
搜索输入 ──▶ 检查 Redis 缓存
                │
                ├──▶ 命中缓存 → 直接返回
                │
                └──▶ 未命中 → 调用 LLM 生成
                         │
                         ├── 成功 ──▶ 存入缓存 + 返回结果
                         └── 失败 ──▶ 返回空结果

结果页 ──▶ 一键收录 ──▶ 弹窗确认(默认取消) ──▶ 写入生词本
```

#### 长按选词翻译（SelectableText 组件）

**技术实现**：
- 使用 ArkUI `Text.copyOption(CopyOptions.InApp)` 启用文本选择
- 使用 `bindSelectionMenu()` 绑定自定义选择菜单
- 使用 `onTextSelectionChange()` 监听选区变化

**组件接口**：
```typescript
// SelectableText.ets
interface SelectableTextCallbacks {
  onPlay: (text: string) => void;
  onAddToVocabulary: (text: string) => void;
  onViewDetail: (text: string) => void;
}

@Component
struct SelectableText {
  @Prop text: string;
  @Prop fontSize: number;
  @Prop fontColor: string | Resource;
  callbacks: SelectableTextCallbacks;
}
```

**选区验证逻辑**：
```typescript
isSelectionValid(): boolean {
  const text = this.selectedText.trim();
  if (text.length === 0) return false;
  // 必须包含韩文或中文字符
  const koreanOrChinese = /[\uAC00-\uD7AF\u1100-\u11FF\u4E00-\u9FFF]/;
  return koreanOrChinese.test(text);
}
```

**快速翻译 API**：
```
GET /api/dict/quick-translate?word={word}&direction=auto
Response: { "word": "...", "translation": "...", "source": "local|ai" }
```

#### 浏览历史导航

**状态管理**：
```typescript
@State browseHistory: string[] = [];      // 浏览历史列表
@State currentHistoryIndex: number = -1;  // 当前词位置
private static readonly MAX_BROWSE_HISTORY: number = 10;
```

**关键方法**：
- `addToBrowseHistory(word)` - 添加到历史（去重+限制10个）
- `onBrowseHistoryClick(word, index)` - 点击历史项跳转
- `performSearchWithoutHistory()` - 执行搜索不重复添加历史

**UI组件**：`HistoryNavBar` Builder - 水平可滑动Scroll + Chip列表

#### 生词本滑动手势

**VocabularyService 扩展**：
```typescript
async reviveWord(hangul: string): Promise<void>  // 复活到待复习
isWordDueForReview(hangul: string): boolean       // 检查是否待复习
```

**ListItem.swipeAction 配置**：
```typescript
.swipeAction({
  end: { builder: () => { this.DeleteSwipeButton(word) } },
  start: this.vocabularyService.isWordDueForReview(word.hangul) 
    ? undefined 
    : { builder: () => { this.ReviveSwipeButton(word) } }
})
```

#### 生词本来源展示

**VocabularyWord.source 字段**：
- `'dictionary'` - 词典搜索添加
- `'selection'` - 选词翻译添加
- `'lesson'` - 学习页添加（预留）

**UI显示**：WordCard 右侧显示 "词典 · 2/3" 或 "选词 · 2/3"

#### 生词本滚动分页

- **分页大小**：每页 20 条
- **向下滚动** (`onReachEnd`) → 加载下一页
- **下拉刷新** (`Refresh.onRefreshing`) → 返回上一页
- **弹簧动效**：`animateTo` + `curves.springMotion(0.5, 0.8)`
- **页头显示**：`📋 待复习 45 个 · 当前 21-40`

#### 生词卡片跳转词典

- **VocabularyContent.onSearchWord** 回调
- **Index.ets** 接收回调，切换到词典Tab，设置 `dictSearchWord`
- **DictContent** 监听 `@Prop @Watch searchWordFromExternal` 触发搜索

#### 复活单词排序

- `reviveWord` 设置 `nextReviewTime = 0`
- 按时间排序后自动排在待复习列表最前

---

### 3.1 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── routers/
│   │   ├── tts.py           # TTS 接口
│   │   ├── dict_ai.py       # 词典AI补充
│   │   ├── content.py       # 内容下载
│   │   └── stats.py         # 统计上报
│   ├── services/
│   │   ├── aliyun_tts.py    # 阿里云TTS封装
│   │   ├── deepseek.py      # Deepseek封装
│   │   └── qwen.py          # 通义千问封装(备用)
│   ├── models/
│   │   └── schemas.py       # Pydantic模型
│   └── utils/
│       └── cache.py         # 缓存工具
├── scripts/
│   ├── build_wordlist.py    # 词表构建脚本
│   └── generate_content.py  # 内容生成脚本
├── data/
│   └── topik1_words.json    # 词表数据
├── requirements.txt
└── Dockerfile
```

### 3.2 API 接口设计

#### 3.2.1 TTS 接口
```
POST /api/tts
Request:
{
  "text": "안녕하세요",
  "lang": "ko"           // ko=韩语
}
Response:
{
  "audio_url": "https://...",  // 音频URL(带签名)
  "duration_ms": 1200
}
或直接返回音频流 (audio/mpeg)
```

#### 3.2.2 词典 AI 补充
```
POST /api/dict/ai
Request:
{
  "word": "사랑",
  "direction": "ko2zh"   // ko2zh / zh2ko
}
Response:
{
  "ai_meaning": "爱，爱情；喜爱",
  "ai_examples": [
    {"ko": "사랑해요", "zh": "我爱你"}
  ],
  "synonyms": ["애정"],
  "antonyms": []
}
```

#### 3.2.2a 词典 SSE 流式搜索
```
GET /api/dict/search/stream?query={query}&direction=auto
Response (SSE stream):
  event: cached / token / done / error
  
  // 缓存命中时
  data: {"type": "cached", "data": {...完整结果...}}
  
  // 流式输出时
  data: {"type": "token", "data": "...JSON片段..."}
  
  // 完成时
  data: {"type": "done", "data": {...完整结果...}}
  
特点:
- 缓存命中即时返回完整结果
- 缓存未命中时逐token流式输出
- 客户端可实时解析显示部分内容
```

#### 3.2.3 内容下载
```
GET /api/content/lesson/{lesson_id}
Response:
{
  "lesson_id": 1,
  "level": 1,
  "words": [...],        // 50个词条完整数据
  "audio_urls": {...},   // 音频预签名URL
  "ai_mnemonics": {...}  // AI联想(可空)
}
```

#### 3.2.4 统计上报
```
POST /api/stats/batch
Request:
{
  "device_id": "xxx",
  "events": [
    {"name": "lesson_complete", "data": {...}, "ts": 1706400000}
  ]
}
```

### 3.3 第三方服务封装

#### Deepseek 调用（带降级）
```python
async def call_deepseek(prompt: str) -> Optional[str]:
    try:
        response = await deepseek_client.chat(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            timeout=10
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"Deepseek failed: {e}, falling back to Qwen")
        return await call_qwen_fallback(prompt)

async def call_qwen_fallback(prompt: str) -> Optional[str]:
    try:
        # 通义千问备用调用
        ...
    except Exception:
        return None  # 静默失败
```

#### 阿里云 TTS 调用
```python
async def text_to_speech(text: str, lang: str = "ko") -> bytes:
    # 使用阿里云语音合成 SDK
    # 韩语使用 voice: "Yeonmi" 或类似
    ...
```

---

## 4. 数据模型设计

### 4.1 词条模型 (WordEntry)

```json
{
  "id": 1,
  "hangul": "사랑",
  "romanization": "sarang",
  "pos": "명사",
  "primary_meaning": "爱，爱情",
  "senses": [
    {"meaning": "爱，爱情", "examples": ["사랑해요 - 我爱你"]},
    {"meaning": "喜爱，热爱", "examples": ["음악을 사랑하다 - 热爱音乐"]}
  ],
  "collocations": ["사랑하다", "사랑에 빠지다"],
  "examples": [
    {"ko": "사랑은 아름다워요.", "zh": "爱情是美丽的。"}
  ],
  "topik_level": 1,
  "freq_rank": 50,
  "lesson_id": 1
}
```

### 4.2 练习题模型 (Quiz)

```json
{
  "type": "basic_recognition",  // 题型
  "word_id": 1,
  "stem": {
    "display": "사랑",
    "audio_url": "..."          // 可选
  },
  "options": [
    {"id": "A", "text": "爱，爱情", "correct": true},
    {"id": "B", "text": "朋友", "correct": false},
    {"id": "C", "text": "家人", "correct": false},
    {"id": "D", "text": "工作", "correct": false}
  ]
}
```

### 4.3 题型定义

| 题型代码 | 名称 | 配比 |
|----------|------|------|
| `basic_recognition` | 基础识别（看词选义） | 25% |
| `context_sense` | 语境义项选择 | 30% |
| `confusion_words` | 易混词辨析 | 25% |
| `collocation_fill` | 搭配填空 | 20% |

听力变体：在以上题型基础上加 `_listening` 后缀（如 `basic_recognition_listening`）

---

## 5. 词表构建方案

### 5.1 数据来源

1. **基础词表**：韩国国立国语院 TOPIK 词汇表（公开资源）
2. **词频排序**：参考《现代韩国语词频词典》

### 5.2 构建流程

```
Step 1: 获取原始词表
        └─▶ TOPIK 1 级约 1000 词（公开资源/爬取整理）

Step 2: 数据清洗
        └─▶ 去重、统一格式、补充词性

Step 3: AI 批量生成
        └─▶ Deepseek 生成：释义、例句、同义词/反义词
        └─▶ 硬规则校验：例句必须包含目标词

Step 4: 罗马音生成
        └─▶ 使用 hangul-romanize 库自动转写

Step 5: 导出 JSON
        └─▶ topik1_words.json (供 App 预置/下载)
```

### 5.3 构建脚本示例

```python
# scripts/build_wordlist.py

async def generate_word_content(word: str) -> dict:
    prompt = f"""
请为韩语单词"{word}"生成以下内容（JSON格式）：
1. primary_meaning: 最常用中文释义（10字以内）
2. senses: 所有义项列表，每项含meaning和1个example
3. examples: 2个TOPIK风格例句，含韩文和中文翻译
4. collocations: 常用搭配（最多3个）

要求：
- 例句必须包含目标词原形或词形变化
- 释义简洁准确
- 输出纯JSON，无解释
"""
    result = await call_deepseek(prompt)
    return validate_and_parse(result, word)
```

---

## 6. 离线策略

### 6.1 下载包内容

| 内容 | 说明 | 存储位置 |
|------|------|----------|
| 词条数据 | 50词完整信息 | RDB |
| 例句 | 包含在词条中 | RDB |
| 练习题模板 | 题型+选项生成规则 | RDB |
| 音频缓存 | TTS 音频文件 | FileSystem |
| AI 联想 | 已生成则包含 | RDB |

### 6.2 自动下载触发

```typescript
// 触发条件
// 1. 进入等级详情页
// 2. 完成一关后

async function triggerAutoDownload() {
  const currentLesson = getCurrentLesson();
  const downloadQueue = [];
  
  for (let i = 1; i <= 3; i++) {
    const nextLesson = currentLesson + i;
    if (!isDownloaded(nextLesson)) {
      downloadQueue.push(nextLesson);
    }
  }
  
  // 后台静默下载
  await downloadLessonsInBackground(downloadQueue);
}
```

### 6.3 离线状态处理

| 功能 | 离线行为 |
|------|----------|
| 已下载关卡学习 | ✅ 正常可用 |
| 生词本查看 | ✅ 正常可用 |
| 复习功能 | ✅ 使用缓存内容 |
| 词典查询 | ⚠️ 仅本地结果 |
| AI 补充 | ❌ 不可用（静默） |
| TTS 播放 | ⚠️ 仅缓存音频 |

---

## 7. 开发里程碑

### Phase 1: 基础框架（1周）
- [ ] 服务端项目初始化
- [ ] App 项目初始化（DevEco Studio）
- [ ] 本地存储层实现
- [ ] 基础 UI 框架（3 Tab）

### Phase 2: 词表与内容（1周）
- [ ] 词表构建脚本
- [ ] TOPIK 1 词表生成（1000词）
- [ ] 练习题生成逻辑
- [ ] 内容下载接口

### Phase 3: 核心功能（2周）
- [ ] 关卡学习流程（预习→练习→通关）
- [ ] 词典功能（本地+AI）
- [ ] 生词本与复习
- [ ] TTS 集成

### Phase 4: 完善与验收（1周）
- [ ] 离线功能验证
- [ ] 每日任务
- [ ] 统计埋点
- [ ] 备份导出

**总计：约 5 周**

---

## 8. 验收检查清单

### 核心链路
- [ ] TOPIK 1 的 20 关可顺序解锁与通关
- [ ] 掌握度判定（答对≥2次）正确
- [ ] 通关阈值 85% 生效
- [ ] 跳过机制可用（≤10词）
- [ ] 加练清单可访问

### 词典功能
- [ ] 精确匹配查询可用
- [ ] 中→韩 返回 Top3
- [ ] Deepseek 补充异步追加
- [ ] 收录弹窗（默认取消）

### 复习功能
- [ ] 固定间隔计划运行
- [ ] 每日 20 上限 + 可追加

### 离线与降级
- [ ] 已下载关卡离线可学
- [ ] TTS 失败静默
- [ ] Deepseek 失败静默

### 统计
- [ ] 本地统计页可查看关键指标

---

## 9. AI精灵助手（小语灵🧚）

### 9.1 架构设计

```
┌─────────────────────────────────────────┐
│         FloatingSpirit.ets              │  悬浮按钮 + 呼吸动画
└─────────────────┬───────────────────────┘
                  │ onClick
┌─────────────────▼───────────────────────┐
│         SpiritChatPanel.ets             │  对话面板UI
├─────────────────────────────────────────┤
│         SpiritChatService.ets           │  历史记录管理
└─────────────────┬───────────────────────┘
                  │ API Call
┌─────────────────▼───────────────────────┐
│         /api/spirit/chat                │  后端多轮对话
├─────────────────────────────────────────┤
│         LLMService.chat_completion      │  LLM调用
└─────────────────────────────────────────┘
```

### 9.2 前端组件

| 组件 | 路径 | 说明 |
|------|------|------|
| FloatingSpirit | components/FloatingSpirit.ets | 悬浮按钮 + 呼吸动画 |
| SpiritChatPanel | components/SpiritChatPanel.ets | 对话面板 + 消息列表 |
| SpiritChatService | services/SpiritChatService.ets | dataPreferences持久化 |

### 9.3 后端API

**POST /api/spirit/chat**

请求：
```json
{
  "messages": [
    {"role": "user", "content": "안녕하세요是什么意思？"},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "怎么发音？"}
  ]
}
```

响应：
```json
{
  "reply": "안녕하세요的韩语发音是...",
  "success": true
}
```

### 9.4 System Prompt

```
你是"小语灵"，一个专业且友好的韩语学习助手。
...（限定韩语学习范围，参见spirit.py）
```

### 9.5 本地存储

Key: `spirit_chat` / `current_session`
```json
{
  "id": "session_xxx",
  "messages": [...],
  "createdAt": 1706947200000,
  "updatedAt": 1706947300000
}
```

---

## 10. UI对齐修复记录（2026-02-09）

### 10.1 主题全局化

- `ThemeManager` 增加订阅/通知机制，主题切换时全局组件同步刷新。
- `Constants` 新增运行时主题状态（`setRuntimeDarkMode`），`COLORS/AppColors` 改为运行时动态取色。
- 启动与切前台流程统一通过 `themeManager.init(...)` 恢复主题，修复深色模式状态不一致问题。

### 10.2 底部 Tab 栏与安全区

- `Index` 页切换为自定义 `BottomTabBar`，支持深浅色背景、边框与选中态联动。
- 底部栏采用系统底部安全区扩展，修复底栏下方白边、固定空隙及遮挡问题。
- 对词典详情底部滚动区域补充额外留白，避免总结内容被底栏遮挡。

### 10.3 关键页面适配

- `ProfileContent`：去除顶部标题，内容上移；登录/注册弹窗深色适配；VIP 订阅确认弹窗替换为系统风格自定义弹窗。
- `DictContent`：例句、近义词、反义词、扩展词汇在深色模式下修复浅底浅字问题。
- `StudyContent`、`SettingsPage`、`StatisticsPage`：统一顶部安全区内边距，修复状态栏重叠。

### 10.4 相关代码位置

- `/Users/mars/sourceCode/personal/ai/LingAI/app/entry/src/main/ets/utils/ThemeManager.ets`
- `/Users/mars/sourceCode/personal/ai/LingAI/app/entry/src/main/ets/utils/Constants.ets`
- `/Users/mars/sourceCode/personal/ai/LingAI/app/entry/src/main/ets/pages/Index.ets`
- `/Users/mars/sourceCode/personal/ai/LingAI/app/entry/src/main/ets/components/ProfileContent.ets`
- `/Users/mars/sourceCode/personal/ai/LingAI/app/entry/src/main/ets/components/DictContent.ets`
- `/Users/mars/sourceCode/personal/ai/LingAI/app/entry/src/main/ets/components/StudyContent.ets`
- `/Users/mars/sourceCode/personal/ai/LingAI/app/entry/src/main/ets/pages/SettingsPage.ets`
- `/Users/mars/sourceCode/personal/ai/LingAI/app/entry/src/main/ets/pages/StatisticsPage.ets`

### 10.5 学习与词典增量修复（2026-02-09）

- `LessonPage.ets`
  - 预习页顶部安全区和标题区域间距优化。
  - “直接练习”由系统 `promptAction.showDialog` 改为页面内自定义确认弹窗，深浅色样式统一。
- `FlashCard.ets`
  - 预习进度文案（如 `1/40`）顶部留白精调，避免贴边。
- `DictContent.ets`
  - 历史词条导航条改为主题色适配，未选中 chip/文本/背景在深色模式可读。
  - 左右方向指示改为轻量非实心箭头风格，减少视觉突兀。
  - 收藏单词列表页头部间距调整，避免标题贴近系统状态栏。
- `SelectableText.ets`
  - 移除默认全选逻辑（`.selection(0, this.text.length)`），修复词典详情页例句最后一条自动高亮问题。
- `StatisticsPage.ets`
  - 打卡区重构为“按月日历 + 选中日学习详情”结构，默认选中当天。
  - 学习概览四项统计卡统一高度与文案基线；学习详情卡改为紧凑布局，避免异常拉伸。
- `SettingsPage.ets`
  - 底部 Tab 栏参数与 `Index.ets` 主栏统一（高度、底部内边距、安全区扩展、下沉偏移），修复页面间栏体高度不一致。
