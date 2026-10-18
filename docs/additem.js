// 设置页的「新增 / 修改关注项」向导：只写个名字，一问一答把关注什么、什么要立刻通知、不想看什么问清楚，
// 最后汇总成一张可以直接改的表，提交到数据库 submit_item()（db/item_requests.sql），下一次更新时写进 items.yaml。
// 名字先去维基数据（Wikidata）查一下：猜它是什么、补上各语言的正式名称、Steam / AniList / TMDB 编号和官网。
// 查不到（没网、被限流、太冷门）也没关系，问题照样一步一步问。
// 页面里 <script id="wl-cfg"> 给出数据库地址、板块一览（sections.yaml：日语名、对号入座的词、小分类的分法和常用值）
// 和每个关注项现在的设置（scripts/render.py 的 render_settings）。板块事先定全，不临时开新板块：按维基数据的说明・名字推荐（都是规则）。
(() => {
  "use strict";
  const CFG = JSON.parse(document.getElementById("wl-cfg").textContent);
  const box = document.getElementById("wiz");
  if (!box) return;

  const LANGS = {"zh-TW": "中文（港台）", "en-US": "英文", "ja-JP": "日文", "ko-KR": "韩文", "zh-CN": "中文（大陆）"};
  const TYPES = {game: "游戏", anime: "动画 / 漫画", show: "电影 / 剧集", event: "艺人演出", product: "具体商品", category: "一类产品"};
  const esc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // 选项的 when：只在名字 / 维基数据说明里提到这些词时才出现（比如「猫相关的」只给跟猫有关的东西）
  const about = re => () => re.test(context());
  function context() {
    const p = wdPick(), o = S.original || {};
    return [S.name, p?.desc, ...(p?.aliases || []), ...Object.values(p?.names || {}), ...(o.keywords || []), o.notes || ""].join(" ");
  }

  // 每种东西可以关注的方面。sec = 选了它就推荐「也放在」这个板块（[板块, 小分类的预设]，ちいかわ选「动画」→ 映像・アニメ）。
  // rec = 「你帮我定」时选它。priority 写进「最关心什么」，urgent 是要紧消息的动词（和名字一起拼成正则），
  // kw 是额外的搜索词（{n} = 名字，{en} / {ja} = 英文 / 日文名），ask 表示还要追问一句
  const KINDS = {
    game: {label: "游戏", hint: "手游、主机、PC 游戏", type: "game", section: "游戏", focus: [
      {rec: true, id: "play", label: "什么时候能玩", hint: "测试招募、上线日期、预约", priority: "什么时候能玩（测试招募、上线日期、预约）",
       urgent: "(测试|測試|封測|内测|β|CBT|テスト|事前登録|預約|预约|上線|上线|正式サービス|配信開始|リリース|發售|发售|release date|launch|beta)"},
      {rec: true, id: "update", label: "版本更新、活动、新角色", hint: "大版本、周年、联动活动", priority: "大版本更新、新角色、周年活动",
       urgent: "(新角色|新キャラ|周年|週年|大型アップデート|大版本|新版本|Ver\\.?\\s?\\d)"},
      {id: "esports", label: "电竞比赛", hint: "赛程、比赛结果、战队", priority: "电竞赛事的日程和结果、战队消息",
       urgent: "(世界大赛|世界賽|決勝|决赛|總決賽|总决赛|World Championship|Worlds|Major|優勝|冠军|冠軍)",
       kw: ["{en} esports", "{ja} 大会", "{n} 電競"]},
      {id: "sale", label: "打折、免费送", hint: "史低、限免", priority: "什么时候打折或限免",
       urgent: "(セール|特價|特价|折扣|降價|降价|史低|免費|免费|無料|sale)"},
      {sec: ["好物", {kind: "キャラクター", owner: "キャラクター"}], id: "collab", label: "联名、周边", hint: "跨界联动、手办、周边", priority: "联名和周边",
       urgent: "(コラボ|联名|聯名|collab|グッズ|周边|周邊|フィギュア)"},
      {id: "story", label: "剧情、角色、世界观", hint: "新剧情、角色设定", priority: "新剧情和角色设定"},
    ]},
    anime: {label: "动画 / 漫画", hint: "番剧、漫画、轻小说", type: "anime", section: "影视", focus: [
      {rec: true, id: "sequel", label: "新一季 / 续作 / 剧场版", hint: "什么时候官宣、定档", priority: "新一季、续作或剧场版什么时候出",
       urgent: "(第\\s?[0-9一二三四五六七八九十]+\\s?(季|期)|続編|续篇|續篇|新作|劇場版|剧场版|映画化|放送決定|定档|定檔|製作決定|制作决定|season \\d|sequel)"},
      {rec: true, id: "air", label: "播出时间、每集更新", hint: "什么时候播、在哪看", priority: "播出时间和每集更新"},
      {sec: ["书刊", {kind: "マンガ"}], id: "manga", label: "漫画连载、单行本", hint: "最新话、出刊、完结", priority: "漫画连载和单行本",
       urgent: "(単行本|单行本|最新刊|最終回|最终话|最終話|完結|完结|休載|休刊)"},
      {sec: ["好物", {kind: "キャラクター", owner: "キャラクター"}], id: "collab", label: "周边、联名、展览", hint: "快闪店、联名商品", priority: "周边、联名和展览",
       urgent: "(コラボ|联名|聯名|展覧会|展览|展覽|POP ?UP|ポップアップ|快闪)"},
      {id: "cast", label: "声优、活动、演唱会", hint: "舞台剧、见面会", priority: "声优活动和演唱会",
       urgent: "(イベント|ライブ|舞台|声優|声优|聲優)"},
    ]},
    show: {label: "电影 / 剧集", hint: "美剧、日剧、电影系列", type: "show", section: "影视", focus: [
      {rec: true, id: "sequel", label: "新一季 / 续集", hint: "续订、官宣", priority: "新一季或续集什么时候出",
       urgent: "(第\\s?[0-9一二三四五六七八九十]+\\s?季|新一季|續訂|续订|renewed|season \\d|sequel|續集|续集|続編)"},
      {rec: true, id: "date", label: "上映 / 播出日期、在哪看", hint: "定档、上线平台", priority: "上映或播出日期、在哪个平台能看",
       urgent: "(定档|定檔|上映日|首播|premiere|release date|公開日|配信開始|上線|上线)"},
      {id: "trailer", label: "预告片", hint: "正式预告、剧照", priority: "预告片", urgent: "(预告|預告|trailer|予告)"},
      {id: "cast", label: "演员、幕后", hint: "选角、导演、采访", priority: "演员和幕后消息"},
    ]},
    artist: {label: "歌手 / 艺人", hint: "乐队、偶像团体、演员", type: "event", section: "演出", focus: [
      {rec: true, id: "live", label: "演唱会、巡演", hint: "尤其是日本 / 大阪附近", priority: "演唱会和巡演（尤其是日本、大阪附近的场次）",
       urgent: "(演唱會|演唱会|巡演|巡迴|ツアー|ライブ|コンサート|concert|tour|公演|ドーム|大阪)"},
      {rec: true, id: "ticket", label: "门票：抽选、发售", hint: "先行抽选、一般发售", priority: "门票怎么买（抽选、发售时间）",
       urgent: "(抽選|抽选|先行|チケット|門票|门票|售票|ticket|一般発売)"},
      {rec: true, id: "music", label: "新歌、新专辑、回归", hint: "MV、回归日期", priority: "新歌、新专辑和回归",
       urgent: "(回归|回歸|컴백|comeback|カムバック|新曲|新歌|新專輯|新专辑|album|リリース|MV)"},
      {id: "fan", label: "见面会、综艺、粉丝活动", hint: "签售、综艺出演", priority: "见面会、综艺和粉丝活动",
       urgent: "(見面會|见面会|ファンミ|fan ?meeting|팬미팅|サイン会|签售)"},
      {id: "collab", label: "联名、代言、周边", hint: "品牌合作", priority: "联名、代言和周边",
       urgent: "(コラボ|联名|聯名|代言|アンバサダー|ambassador)"},
    ]},
    sports: {label: "运动 / 赛事", hint: "比赛、联赛、运动项目", type: "category", section: "运动", focus: [
      {rec: true, id: "schedule", label: "赛程、门票", hint: "什么时候比、怎么买票", priority: "赛程和门票",
       urgent: "(日程|赛程|賽程|チケット|门票|門票|抽選|発売)"},
      {rec: true, id: "result", label: "比赛结果", hint: "谁赢了、名次", priority: "比赛结果",
       urgent: "(優勝|优胜|冠军|冠軍|決勝|决赛|決賽|champion|wins)"},
      {id: "player", label: "某个选手 / 队伍", hint: "下一步填名字", priority: "", ask: "player"},
      {id: "watch", label: "转播、在哪看直播", hint: "电视台、网络直播", priority: "在哪看转播和直播"},
      {id: "join", label: "自己去玩", hint: "场地、装备、季节开放", priority: "自己去玩：场地、装备、开放时间",
       urgent: "(オープン|開業|开业|開幕|开放|營業|营业|シーズン)"},
    ]},
    character: {label: "角色 / IP", hint: "三丽鸥、宝可梦、蜡笔小新这类角色", type: "category", section: "好物", focus: [
      {id: "collab", label: "联名商品", hint: "和服装、杂货、零食品牌的联名", priority: "新的联名商品什么时候出、怎么买", rec: true,
       urgent: "(コラボ|联名|聯名|collab|×)"},
      {id: "goods", label: "新周边、新品", hint: "毛绒、文具、扭蛋、一番赏", priority: "新周边和新品", rec: true,
       urgent: "(新商品|新作|発売|发售|發售|登場|ぬいぐるみ|一番くじ|ガチャ|扭蛋|一番賞|一番赏)"},
      {id: "popup", label: "快闪店、主题咖啡、展览", hint: "期间限定店、主题餐厅", priority: "快闪店、主题咖啡和展览（尤其是日本、大阪附近）", rec: true,
       urgent: "(ポップアップ|POP ?UP|快闪|快閃|カフェ|咖啡|展覧会|展览|展覽|期間限定ショップ)"},
      {id: "lottery", label: "抽选、限定、预约", hint: "要抢的东西", priority: "抽选、限定品和预约怎么买",
       urgent: "(抽選|抽选|限定|予約|预约|預約|受注)"},
      {sec: ["影视", {kind: "アニメ"}], id: "media", label: "动画、电影、活动", hint: "新动画、剧场版、生日、周年庆", priority: "新动画、活动和周年纪念",
       urgent: "(アニメ|动画|動畫|周年|週年|アニバーサリー|anniversary|誕生日|生日)"},
    ]},
    book: {label: "书 / 杂志 / 漫画单行本", hint: "杂志、小说、漫画、写真集", type: "product", section: "书刊", focus: [
      {rec: true, id: "release", label: "发售日、新刊", hint: "下一期、新卷什么时候出", priority: "发售日和新刊",
       urgent: "(発売日|発売|最新号|最新刊|新刊|新卷|发售|發售|release|on sale|刊行)"},
      {rec: true, id: "furoku", label: "付录、限定版", hint: "附赠品、特装版", priority: "付录和限定版（附赠什么、怎么买）",
       urgent: "(付録|付录|附錄|附录|特装版|特裝版|限定版|増刊|增刊|特別号|特别号)"},
      {id: "cover", label: "封面、特集", hint: "谁上封面、做了什么特集", priority: "封面人物和特集",
       urgent: "(表紙|封面|cover|特集|特辑|特輯)"},
      {id: "media", label: "改编、得奖", hint: "动画化、影视化、得奖", priority: "改编和得奖",
       urgent: "(アニメ化|映像化|実写化|映画化|ドラマ化|改编|改編|受賞|得奖|得獎|award)"},
      {id: "event", label: "签售、展览、活动", hint: "作者签售、原画展", priority: "签售、展览和活动",
       urgent: "(サイン会|签售|簽售|原画展|展覧会|展览|展覽|イベント)"},
    ]},
    food: {label: "吃的 / 喝的", hint: "咖啡店、甜点、餐厅、零食", type: "product", section: "美食", focus: [
      {rec: true, id: "new", label: "新品、季节限定", hint: "新口味、季节菜单", priority: "新品和季节限定",
       urgent: "(新作|新品|新発売|新発売|新商品|季節限定|期間限定|限定|新口味|新菜单|新菜單|new menu)"},
      {rec: true, id: "collab", label: "联名", hint: "和动画、角色的联名", priority: "联名", urgent: "(コラボ|联名|聯名|collab)"},
      {id: "shop", label: "开店、关店", hint: "新店、日本 / 大阪附近", priority: "开店和关店（尤其是日本、大阪附近）",
       urgent: "(オープン|開店|开店|開業|新店|閉店|关店|閉店)"},
      {id: "sale", label: "优惠、活动", hint: "打折、买一送一", priority: "优惠和活动", urgent: "(セール|割引|半額|优惠|優惠|キャンペーン|折扣)"},
    ]},
    place: {label: "去的地方 / 展览", hint: "主题乐园、美术馆、展览、旅行地", type: "category", section: "出行", focus: [
      {rec: true, id: "event", label: "新活动、新展览", hint: "期间限定活动、特别展", priority: "新的活动和展览",
       urgent: "(開催|开幕|開幕|開催決定|特別展|企画展|新エリア|新アトラクション|イベント)"},
      {rec: true, id: "ticket", label: "门票、预约", hint: "什么时候开卖、要不要抽选", priority: "门票和预约",
       urgent: "(チケット|門票|门票|予約|预约|預約|抽選|抽选|発売)"},
      {id: "open", label: "开业、闭馆、休园", hint: "营业时间变化", priority: "开业、闭馆和营业时间",
       urgent: "(オープン|開業|开业|閉館|闭馆|休園|休馆|リニューアル)"},
      {id: "crowd", label: "人多不多、交通", hint: "排队、交通方式", priority: "人流和交通"},
    ]},
    product: {label: "商品 / 品牌", hint: "手机、杯子、衣服、品牌", type: "product", section: "好物", focus: [
      {rec: true, id: "new", label: "新品、新款发售", hint: "新色、新型号", priority: "新品和新款什么时候发售",
       urgent: "(新品|新作|新款|発売|発表|发售|發售|上市|launch|release|新色)"},
      {rec: true, id: "sale", label: "降价、促销", hint: "打折、优惠券", priority: "什么时候降价促销",
       urgent: "(セール|特價|特价|折扣|降價|降价|sale|値下げ|半額|半价)"},
      {rec: true, id: "collab", label: "联名、限定款", hint: "季节限定、地区限定", priority: "联名和限定款",
       urgent: "(コラボ|联名|聯名|限定|collab)"},
      {id: "lottery", label: "福袋、抽选、预约", hint: "要抢的东西", priority: "福袋、抽选和预约怎么买",
       urgent: "(福袋|抽選|抽选|予約|预约|預約|HAPPY ?BOX)"},
      {id: "cat", label: "猫相关的", hint: "猫柄、猫咪造型、猫用", priority: "猫系商品（猫柄、猫咪造型、猫角色联名）",
       urgent: "(ねこ|ネコ|猫|貓|キャット|cat)", when: about(/猫|ねこ|ネコ|貓|キャット|\bcats?\b|kitty|ペット|宠物|寵物|\bpets?\b/i)},
      {id: "review", label: "评测、好不好用", hint: "开箱、口碑", priority: "评测和口碑"},
    ]},
  };
  const KIND_OF_TYPE = {game: "game", anime: "anime", show: "show", event: "artist", product: "product", category: "product"};

  // ---------- 板块（sections.yaml）：对号入座 ----------
  const SECS = CFG.sections || [];
  const secOf = key => SECS.find(x => x.key === key) || SECS.find(x => x.key === "其他") || {key, ja: key, schemes: []};
  const secRe = x => { try { return x.words ? new RegExp(x.words, "i") : null; } catch (_) { return null; } };
  const vOf = v => typeof v === "object" ? v.v : v;
  // 值が説明・名字に出てくるか（「家具・インテリア」は片方でも。英字は単語として。{v, re} は re でも）
  function says(v, t) {
    if (typeof v === "object") { try { if (v.re && new RegExp(v.re, "i").test(t)) return true; } catch (_) {} v = v.v; }
    return String(v).split(/[・/]/).filter(Boolean).some(p => /^[\x00-\x7f]+$/.test(p) ? new RegExp(`\\b${esc(p)}\\b`, "i").test(t) : t.includes(p));
  }
  // 它自己本来是哪个板块：「角色 / IP」一定是グッズ（ちいかわ的维基说明是「漫画」，但关注的是联名・周边）；
  // 其他按说明・名字里的词（表从上到下，先命中的算）；都没命中按「这是什么」
  function naturalSection() {
    if (S.ans.kind === "character") return "好物";
    const t = context();
    const hit = SECS.find(x => { const re = secRe(x); return re && re.test(t); });
    return hit ? hit.key : kindOf().section;
  }
  // 有上级就跟着上级的板块（目录上挂在上级下面），没有就是它自己本来的板块
  const parentItem = () => S.ans.parent ? (CFG.items || []).find(i => i.name === S.ans.parent) : null;
  const guessSection = () => parentItem()?.section || naturalSection();
  // 上级候补：已有的、自己没有上级的关注项里，名字或搜索词出现在新项的名字・维基数据里的（「ちいかわ 映像」→ ちいかわ）
  const tops = () => (CFG.items || []).filter(i => !i.parent && i.name !== S.name);
  function parentCandidates() {
    const t = context().toLowerCase();
    return tops().filter(i => [i.name, ...(i.keywords || [])].some(w => w && w.length >= 2 && t.includes(String(w).toLowerCase())));
  }
  // 每种分法选一个值：说明・名字里出现了的，没有就第一个
  function guessSubs(key) {
    const t = context(), out = {};
    // 挂在别的板块的上级下面时（ちいかわ アニメ → グッズ），第一种分法写它自己本来的类别（アニメ），目录上名字旁标出来
    const nat = naturalSection();
    if (parentItem() && nat !== key) {
      const own = Object.values(guessSubs(nat))[0];
      const first = (secOf(key).schemes || [])[0];
      if (own && first) out[first.id] = own;
    }
    // 其他的分法跟上级一样（あつ森 映画 → プラットフォームはあつ森と同じ）
    for (const [k, v] of Object.entries(parentItem()?.subs || {})) if (!out[k] && parentItem().section === key) out[k] = v;
    for (const sc of secOf(key).schemes || []) {
      if (out[sc.id]) continue;
      const vals = sc.values || [];
      // 「角色 / IP」はキャラクターという値があればそれ（ちいかわ → グッズ・キャラクター）
      const pick = (S.ans.kind === "character" ? vals.find(v => vOf(v) === "キャラクター") : null) ?? vals.find(v => says(v, t)) ?? vals[0];
      if (pick != null) out[sc.id] = vOf(pick);
    }
    return out;
  }

  // 「也放在」的推荐：选了的关注方面带 sec 的板块（ちいかわ：选「动画、电影、活动」→ 映像）。主板块（版面所在）除外
  const alsoRec = main => [...new Set(chosenFocus().filter(f => f.sec && f.sec[0] !== main).map(f => f.sec[0]))];
  const secsNow = () => S.ans.sections || [S.ans.section || guessSection(), ...alsoRec(S.ans.section || guessSection())];
  // 也放在的板块里的小分类：按关注方面的预设，其他按说明・名字
  function alsoSubs(key) {
    const pre = chosenFocus().find(f => f.sec && f.sec[0] === key)?.sec[1] || {};
    const base = guessSubs(key);
    return Object.fromEntries((secOf(key).schemes || []).map(sc => [sc.id, pre[sc.id] || base[sc.id]]));
  }

  const EXCLUDES = [
    {id: "resale", rec: true, label: "转卖、二手", words: ["転売", "メルカリ", "中古", "二手", "轉賣", "转卖", "resale"]},
    {id: "guide", label: "攻略、抽卡教学、排行榜", words: ["攻略", "リセマラ", "ガチャ", "抽卡", "tier list", "最強ランキング"], kinds: ["game", "anime"]},
    {id: "roundup", rec: true, label: "带货清单、合集、推荐榜", words: ["おすすめ", "まとめ", "合集", "懶人包", "懒人包", "ランキング", "推薦"]},
    {id: "rumor", label: "传闻、爆料", words: ["リーク", "leak", "爆料", "傳聞", "传闻", "rumor", "噂"]},
    {id: "spoiler", label: "剧透", words: ["ネタバレ", "剧透", "劇透", "spoiler"], kinds: ["game", "anime", "show"]},
  ];

  // ---------- 维基数据 ----------
  const WD = "https://www.wikidata.org/w/api.php";
  const WD_LANGS = ["zh", "zh-hans", "zh-cn", "zh-hant", "zh-tw", "zh-hk", "ja", "ko", "en"];
  const wd = async (params, ms = 8000) => {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
    try {
      const r = await fetch(`${WD}?${new URLSearchParams({...params, format: "json", origin: "*"})}`, {signal: ctl.signal});
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } finally { clearTimeout(t); }
  };
  const KIND_BY_QID = {
    Q7889: "game", Q7058673: "game", Q1107: "anime", Q8274: "anime", Q63952888: "anime", Q21198342: "anime",
    Q11424: "show", Q5398426: "show", Q24856: "show", Q215380: "artist", Q641066: "artist", Q216337: "artist", Q177220: "artist",
    Q13406554: "sports", Q18608583: "sports", Q349: "sports", Q431289: "product", Q2424752: "product",
    Q783794: "product", Q4830453: "product", Q167270: "product",
    Q95074: "character", Q15773347: "character", Q1114461: "character", Q15632617: "character", Q1569167: "character",
  };
  const KIND_BY_TEXT = [
    ["character", /角色|キャラクター|character|mascot|吉祥物|マスコット|サンリオ|三丽鸥|三麗鷗|Sanrio/i],
    ["game", /游戏|遊戲|ゲーム|video game|game/i],
    ["anime", /动画|動畫|アニメ|anime|漫画|漫畫|マンガ|manga|轻小说|ライトノベル/i],
    ["show", /电视剧|電視劇|剧集|劇集|ドラマ|television series|TV series|电影|電影|映画|film|movie/i],
    ["artist", /歌手|乐队|樂團|组合|組合|团体|團體|偶像|singer|band|girl group|boy band|idol|rapper|アイドル|グループ|歌手|演员|演員|actor|actress/i],
    ["sports", /锦标赛|錦標賽|公开赛|公開賽|联赛|聯賽|大会|tournament|championship|league|运动|運動|スポーツ|sport|球员|選手|player/i],
    ["product", /品牌|公司|手机|手機|产品|產品|brand|company|smartphone|product|メーカー|ブランド/i],
  ];
  const ORIGIN_LANG = {Q17: "ja-JP", Q884: "ko-KR", Q148: "zh-CN", Q865: "zh-TW", Q8646: "zh-TW", Q30: "en-US", Q145: "en-US"};
  const claim = (ent, p) => (ent.claims?.[p] || []).map(c => c.mainsnak?.datavalue?.value).filter(v => v != null);
  const label = (ent, langs) => { for (const l of langs) { const v = ent.labels?.[l]?.value; if (v) return v; } return ""; };
  const desc = ent => label({labels: ent.descriptions}, ["zh-hans", "zh", "zh-cn", "zh-hant", "zh-tw", "ja", "en"]);

  async function lookup(name) {
    const found = [];
    const lists = await Promise.allSettled(["zh", "ja", "en"].map(language =>
      wd({action: "wbsearchentities", search: name, language, uselang: "zh", type: "item", limit: 5})));
    for (const l of lists) for (const x of (l.value?.search || [])) if (!found.includes(x.id)) found.push(x.id);
    if (!found.length) return lists.every(l => l.status === "rejected") ? null : [];
    const got = await wd({action: "wbgetentities", ids: found.slice(0, 6).join("|"), props: "labels|aliases|descriptions|claims",
                          languages: WD_LANGS.join("|")});
    return found.slice(0, 6).map(id => got.entities?.[id]).filter(Boolean).map(ent => facts(ent));
  }

  function facts(ent) {
    const zhHant = label(ent, ["zh-tw", "zh-hk", "zh-hant"]), zhHans = label(ent, ["zh-cn", "zh-hans", "zh"]);
    const ja = label(ent, ["ja"]), ko = label(ent, ["ko"]), en = label(ent, ["en"]);
    const kinds = claim(ent, "P31").map(v => KIND_BY_QID[v.id]).filter(Boolean);
    const d = [desc(ent), ent.descriptions?.en?.value || ""].join(" ");
    const bySec = SECS.find(x => { const re = secRe(x); return re && re.test(d); });
    const kind = kinds[0] || (KIND_BY_TEXT.find(([, re]) => re.test(d)) || [])[0] || (bySec && KINDS[bySec.kind] ? bySec.kind : "");
    const origin = [...claim(ent, "P495"), ...claim(ent, "P17"), ...claim(ent, "P27"), ...claim(ent, "P740")]
      .map(v => ORIGIN_LANG[v.id]).filter(Boolean);
    const aliases = Object.entries(ent.aliases || {}).filter(([l]) => WD_LANGS.includes(l))
      .flatMap(([, list]) => list.map(a => a.value)).filter(a => a.length >= (/[぀-鿿가-힯]/.test(a) ? 2 : 4) && a.length <= 40);
    const tmdb = claim(ent, "P4983")[0] ? `tv/${claim(ent, "P4983")[0]}` : claim(ent, "P4947")[0] ? `movie/${claim(ent, "P4947")[0]}` : "";
    return {
      id: ent.id, title: zhHans || zhHant || en || ja || ent.id, desc: desc(ent) || ent.descriptions?.en?.value || "",
      names: {zhHans, zhHant, ja, ko, en}, aliases: [...new Set(aliases)].slice(0, 8), kind, origin: [...new Set(origin)],
      steam: claim(ent, "P1733")[0] || "", anilist: claim(ent, "P8729")[0] || "", anilistManga: claim(ent, "P8731")[0] || "",
      tmdb, site: claim(ent, "P856")[0] || "",
    };
  }

  // ---------- 状态 ----------
  let S;   // {mode, name, step, ans: {...}, wd, wdState, original, draft}
  const fresh = () => ({mode: "add", name: "", step: 0, ans: {}, auto: {}, wd: null, wdState: "idle", draft: null, original: null});

  const kindOf = () => KINDS[S.ans.kind] || KINDS.product;
  const focusOpts = () => kindOf().focus.filter(f => !f.when || f.when());
  const chosenFocus = () => focusOpts().filter(f => (S.ans.focus || []).includes(f.id));
  const wdPick = () => (S.wd || []).find(x => x.id === S.ans.which) || null;

  // 问题清单（add 模式从第 0 问开始；edit 模式「重新问一遍」从 kind 开始）
  const STEPS = [
    {id: "name", when: () => S.mode === "add", render: askName},
    {id: "which", when: () => S.mode === "add" && S.wdState !== "off", render: askWhich},
    {id: "kind", render: () => single("kind", "这是什么？", guessHint(),
      Object.entries(KINDS).map(([v, k]) => ({v, label: k.label, hint: k.hint})))},
    {id: "focus", render: () => multi("focus", `你关注「${S.name}」的哪方面？`, "可以多选。会按这个给消息排序：直接回答这些的新消息排最前面。",
      focusOpts().map(f => ({v: f.id, label: f.label, hint: f.hint})), {other: "其他（自己写）", min: 1})},
    {id: "player", when: () => (S.ans.focus || []).includes("player"), render: () => text("player",
      "关注哪个选手 / 队伍？", "写名字，几个就用逗号隔开。会加进搜索词，只留提到他们的消息。", "如：大坂なおみ, 錦織圭")},
    {id: "urgent", when: () => chosenFocus().some(f => f.urgent), render: () => multi("urgent",
      "哪些消息要当天推到 Discord？", "其余的只在简报和每周一的周报里。传闻、Reddit 帖子不算要紧消息。",
      [...chosenFocus().filter(f => f.urgent).map(f => ({v: f.id, label: f.label, hint: f.hint})),
       {v: "none", label: "都不用，周报里看就行", only: true}])},
    {id: "exclude", render: () => multi("exclude", "这些不想看？", "标题里有这些词的直接丢掉。",
      [...EXCLUDES.filter(x => !x.kinds || x.kinds.includes(S.ans.kind)).map(x => ({v: x.id, label: x.label, hint: x.words.slice(0, 4).join("、")})),
       {v: "none", label: "都可以看", only: true}])},
    {id: "langs", render: () => multi("langs", "看哪些语言的新闻？", langHint(),
      Object.entries(LANGS).map(([v, l]) => ({v, label: l, hint: v === "zh-CN" ? "大陆网站常拦海外、图片防盗链，一般不用" : ""})), {min: 1})},
    {id: "parent", when: () => tops().length > 0, render: askParent},
    {id: "section", when: () => !S.ans.parent, render: askSections},
    {id: "subs", render: askSubs},
    {id: "size", when: () => S.mode === "add", render: () => single("size", "每期给它多大篇幅？", "以后在上面的列表里随时能改。", [
      {v: "S", label: "S · 少", hint: "每期最多 3 条，大约一行"}, {v: "M", label: "M · 中等", hint: "每期最多 5 条"},
      {v: "L", label: "L · 多", hint: "每期最多 8 条，满满一整屏"}])},
    {id: "review", render: review},
  ];
  const live = () => STEPS.filter(s => !s.when || s.when());
  const LABELS = {name: "名字", which: "是哪个", kind: "这是", focus: "关注", player: "选手 / 队伍", urgent: "立刻通知",
                  exclude: "不看", langs: "语言", parent: "上级", section: "板块", subs: "小分类", size: "篇幅"};

  function defaults(id) {
    const pick = wdPick();
    if (id === "kind") return pick?.kind || (S.original ? KIND_OF_TYPE[S.original.type] : "") || "";
    if (id === "urgent") return chosenFocus().filter(f => f.urgent).map(f => f.id);
    if (id === "langs") return [...new Set(["zh-TW", "en-US", ...(pick?.origin || []).filter(l => l !== "zh-CN")])];
    if (id === "section") return S.ans.parent ? guessSection() : S.original?.section || guessSection();
    if (id === "sections") return S.original ? [S.original.section, ...Object.keys(S.original.also || {})] : secsNow();
    if (id === "parent") return S.original ? S.original.parent || "" : parentCandidates()[0]?.name || "";
    if (id === "subs") { const sec = S.ans.section || guessSection();
                         return sec === S.original?.section && S.original?.subs ? {...S.original.subs} : guessSubs(sec); }
    if (id === "size") return "M";
    return undefined;
  }
  // 「不确定，你帮我定」：按维基数据的猜测和每类东西最常见的关注点替你选
  function autoValue(id) {
    if (id === "which") return S.wd?.[0]?.id || "";
    if (id === "kind") return defaults("kind") || "product";
    if (id === "focus") { const r = focusOpts().filter(f => f.rec).map(f => f.id); return r.length ? r : focusOpts().slice(0, 2).map(f => f.id); }
    if (id === "urgent") { const r = chosenFocus().filter(f => f.urgent && f.rec).map(f => f.id); return r.length ? r : defaults("urgent"); }
    if (id === "exclude") return EXCLUDES.filter(x => x.rec && (!x.kinds || x.kinds.includes(S.ans.kind))).map(x => x.id);
    return defaults(id);
  }
  function autoText(id) {
    const v = autoValue(id);
    if (id === "which") return (S.wd || []).find(x => x.id === v)?.title || "不用查";
    if (id === "kind") return KINDS[v]?.label || "";
    if (id === "focus") return focusOpts().filter(f => v.includes(f.id)).map(f => f.label).join("、");
    if (id === "urgent") return chosenFocus().filter(f => v.includes(f.id)).map(f => f.label).join("、") || "不用";
    if (id === "exclude") return EXCLUDES.filter(x => v.includes(x.id)).map(x => x.label).join("、") || "都看";
    if (id === "langs") return v.map(l => LANGS[l]).join("、");
    if (id === "section") return [v, ...alsoRec(v)].map(k => secOf(k).ja).join(" ＋ ");
    if (id === "parent") return v || "不属于";
    if (id === "subs") return Object.values(v || {}).join(" · ");
    return v || "";
  }
  const AUTO_STEPS = ["which", "kind", "focus", "urgent", "exclude", "langs", "parent", "section", "subs", "size"];
  function autoRest() {   // 「剩下的都交给你」：从这一问开始，没回答的都替你选，直接到汇总
    for (let i = S.step, steps = live(); i < steps.length; i++, steps = live()) {
      const id = steps[i].id;
      if (AUTO_STEPS.includes(id) && (S.ans[id] == null || i === S.step || S.auto[id])) {
        S.ans[id] = autoValue(id); S.auto[id] = true;
        if (id === "section") { S.ans.sections = [S.ans.section, ...alsoRec(S.ans.section)]; delete S.ans.also; }
      }
    }
    S.touched = true; S.step = live().length - 1; S.draft = build(); draw();
  }

  const guessHint = () => {
    const p = wdPick();
    if (p?.kind) return `按维基数据猜是「${KINDS[p.kind].label}」${p.desc ? `（${p.desc}）` : ""}，不对就改。`;
    return "选最接近的一类，后面的问题会跟着变。";
  };
  const langHint = () => {
    const o = (wdPick()?.origin || []).filter(l => l !== "zh-CN");
    return o.length ? `它来自${o.map(l => LANGS[l].replace(/（.*）/, "")).join("、")}，已经帮你勾上。` : "中文默认用港台媒体。";
  };

  // ---------- 画面 ----------
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "class") el.className = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    el.append(...kids.flat().filter(k => k != null && k !== false));
    return el;
  };

  function draw() {
    const steps = live(), step = steps[Math.min(S.step, steps.length - 1)];
    const title = S.mode === "edit" ? `修改「${S.name}」` : "＋ 新增关注项";
    const asked = S.mode === "add" || S.ans.focus;   // 修改时直接到汇总的，没有回答过问题
    // 已经回答的：一个问题一个方块，从左到右排（窄屏从上到下），点方块回到那一问重选
    const trail = h("ol", {class: "trail", "aria-label": "已经回答的，点一下可以改"},
      (asked ? steps.slice(0, S.step) : []).map((s, i) => s.id === "review" ? null : h("li", {}, h("button", {type: "button", onclick: () => go(i),
        class: S.auto[s.id] ? "auto" : null, title: "点一下改这一项"},
        h("span", {}, `${i + 1} · ${LABELS[s.id] || s.id}${S.auto[s.id] ? " · 你帮我定的" : ""}`), h("b", {}, answerText(s.id) || "—")))));
    box.replaceChildren(h("h2", {}, title), trail, step.render(), queueList);
    const first = box.querySelector(".q input[type=text], .q .opt[aria-pressed=true], .q .opt, .rv input, .rv select");
    if (first && S.touched) first.focus({preventScroll: true});
  }

  function answerText(id) {
    const a = S.ans[id];
    if (id === "name") return S.name;
    if (id === "which") return wdPick()?.title || "不用查";
    if (id === "kind") return KINDS[a]?.label || "";
    if (id === "section") return a ? [a, ...(S.ans.sections || []).filter(k => k !== a)].map(k => secOf(k).ja).join(" ＋ ") : "";
    if (id === "parent") return a || "不属于";
    if (id === "subs") return Object.values(a || {}).join(" · ");
    if (id === "focus") return [...chosenFocus().map(f => f.label), S.ans.focus_other].filter(Boolean).join("、");
    if (id === "urgent") return (a || []).includes("none") ? "不用" : chosenFocus().filter(f => (a || []).includes(f.id)).map(f => f.label).join("、");
    if (id === "exclude") return (a || []).includes("none") ? "都看" : EXCLUDES.filter(x => (a || []).includes(x.id)).map(x => x.label).join("、");
    if (id === "langs") return (a || []).map(l => LANGS[l]).join("、");
    return Array.isArray(a) ? a.join("、") : a || "";
  }

  const no = () => { const steps = live().filter(s => s.id !== "review"); return `第 ${S.step + 1} / ${steps.length} 问`; };
  const go = i => { S.touched = true; S.step = i; draw(); };
  const next = () => { S.touched = true; S.step = Math.min(S.step + 1, live().length - 1); if (live()[S.step].id === "review") S.draft = build(); draw(); };
  const back = () => { if (S.step > 0) { S.touched = true; S.step--; draw(); } };
  const nav = (ok, label = "下一步") => h("div", {class: "wnav"},
    S.step > 0 ? h("button", {type: "button", onclick: back}, "← 上一步") : null,
    h("button", {type: "button", class: "main", disabled: !ok, onclick: next}, label),
    AUTO_STEPS.includes(live()[S.step]?.id) ? h("button", {type: "button", onclick: autoRest, title: "没回答的问题都按推荐选好，直接看汇总"}, "剩下的都交给你") : null,
    S.mode === "edit" ? h("button", {type: "button", onclick: () => { S.step = live().length - 1; S.draft = build(); draw(); }}, "跳到最后") : null,
    h("button", {type: "button", onclick: reset}, "取消"));

  function askName() {
    const input = h("input", {type: "text", maxlength: 80, value: S.name, placeholder: "如：原神、鬼灭之刃、ILLIT、大阪马拉松",
                              "aria-label": "名字"});
    const submit = () => {
      const name = input.value.trim();
      if (!name) { input.focus(); return; }
      if (name !== S.name) { S.name = name; S.ans = {}; S.wd = null; S.wdState = "loading"; startLookup(name); }
      next();
    };
    input.addEventListener("keydown", ev => { if (ev.key === "Enter" && !ev.isComposing) { ev.preventDefault(); submit(); } });
    return h("div", {class: "q"}, h("span", {class: "no"}, "第 1 问"), h("h3", {}, "想关注什么？"),
      h("p", {}, "只写名字就行。接下来一步一步问你关注它的哪方面、什么要立刻通知、不想看什么，最后汇总给你看，都能改。"),
      input, h("div", {class: "wnav"}, h("button", {type: "button", class: "main", onclick: submit}, "下一步"),
      S.name ? h("button", {type: "button", onclick: reset}, "取消") : null));
  }

  function startLookup(name) {
    lookup(name).then(list => {
      if (S.name !== name) return;
      S.wd = list || []; S.wdState = list === null ? "fail" : "done";
      if (S.wd.length && S.ans.which == null) S.ans.which = S.wd[0].id;
      if (live()[S.step]?.id === "which") draw();
    }).catch(() => { if (S.name === name) { S.wd = []; S.wdState = "fail"; if (live()[S.step]?.id === "which") draw(); } });
  }

  function askWhich() {
    const head = [h("span", {class: "no"}, no()), h("h3", {}, `你说的「${S.name}」是哪一个？`)];
    if (S.wdState === "loading") {
      return h("div", {class: "q"}, ...head, h("p", {}, "正在维基数据里查各语言的正式名称…"),
        h("div", {class: "wnav"}, h("button", {type: "button", onclick: back}, "← 上一步"),
          h("button", {type: "button", class: "main", onclick: () => { S.wdState = "off"; S.ans.which = ""; S.step--; next(); }}, "不查了，直接下一步")));
    }
    if (!S.wd?.length) {
      return h("div", {class: "q"}, ...head,
        h("p", {}, S.wdState === "fail" ? "维基数据现在连不上，没关系：搜索词就先用名字，最后可以自己补。" : "维基数据里没查到，没关系：搜索词就先用名字，最后可以自己补。"),
        nav(true));
    }
    const opts = [...S.wd.map(x => ({v: x.id, label: x.title + (x.names.ja && x.names.ja !== x.title ? ` · ${x.names.ja}` : ""), hint: x.desc || "（没有说明）"})),
                  {v: "", label: "都不是", hint: "不用查了，搜索词先用名字"}];
    return single("which", head[1].textContent, "选对的那个，会自动补上中日韩英的正式名称、官网等。", opts);
  }

  function options(id, opts, multiSel) {
    const cur = S.ans[id] ?? defaults(id) ?? (multiSel ? [] : "");
    if (S.ans[id] == null && cur !== "" && !(Array.isArray(cur) && !cur.length)) S.ans[id] = cur;
    return h("div", {class: "opts", role: multiSel ? "group" : "radiogroup"}, opts.map(o => h("button", {
      type: "button", class: "opt", "aria-pressed": String(multiSel ? (S.ans[id] || []).includes(o.v) : S.ans[id] === o.v),
      onclick: () => {
        S.auto[id] = false;
        if (id === "kind" && S.ans.kind !== o.v) { delete S.ans.focus; delete S.ans.urgent; delete S.ans.exclude; }
        if (id === "section" && S.ans.section !== o.v) delete S.ans.subs;
        if (id === "parent" && S.ans.parent !== o.v) { delete S.ans.subs; S.ans.section = o.v ? (CFG.items.find(i => i.name === o.v) || {}).section : undefined; }
        if (!multiSel) { S.ans[id] = o.v; next(); return; }
        let v = [...(S.ans[id] || [])];
        v = v.includes(o.v) ? v.filter(x => x !== o.v) : o.only ? [o.v] : [...v.filter(x => !opts.find(p => p.v === x)?.only), o.v];
        S.ans[id] = v; draw();
      }}, o.label, o.hint ? h("small", {}, o.hint) : null)),
      AUTO_STEPS.includes(id) ? h("button", {type: "button", class: "opt auto", "aria-pressed": String(!!S.auto[id]),
        onclick: () => { S.ans[id] = autoValue(id); S.auto[id] = true; next(); }},
        "不确定，你帮我定", h("small", {}, `会选：${autoText(id) || "—"}`)) : null);
  }

  function single(id, ask, hint, opts) {
    const body = [h("span", {class: "no"}, no()), h("h3", {}, ask), hint ? h("p", {}, hint) : null, options(id, opts, false)];
    body.push(nav(S.ans[id] != null || id === "which", "下一步"));
    return h("div", {class: "q"}, ...body);
  }

  // 板块：可以多选。版面只有一个，放在「主板块」；其他板块的目录里放「乗換」的站，点了跳到同一个版面（同一条新闻只出现一次）。
  // 推荐：它自己本来的板块 ＋ 选了的关注方面带的板块（ちいかわ：グッズ ＋「动画、电影、活动」→ 映像）
  function askSections() {
    if (!S.ans.sections) S.ans.sections = defaults("sections");
    if (!S.ans.section || !S.ans.sections.includes(S.ans.section)) S.ans.section = S.ans.sections[0];
    const rec = new Set([guessSection(), ...alsoRec(guessSection())]);
    const toggle = k => {
      const cur = S.ans.sections;
      S.ans.sections = cur.includes(k) ? cur.filter(x => x !== k) : [...cur, k];
      if (!S.ans.sections.includes(S.ans.section)) S.ans.section = S.ans.sections[0];
      S.auto.section = false; delete S.ans.subs; delete S.ans.also; draw();
    };
    const chosen = S.ans.sections;
    const main = chosen.length > 1 ? h("div", {class: "subrow"}, h("h4", {}, "版面放在哪个？（主板块）"),
      h("div", {class: "opts", role: "radiogroup"}, chosen.map(k => h("button", {type: "button", class: "opt", "aria-pressed": String(S.ans.section === k),
        onclick: () => { S.ans.section = k; delete S.ans.subs; delete S.ans.also; draw(); }}, secOf(k).ja)))) : null;
    return h("div", {class: "q"}, h("span", {class: "no"}, no()), h("h3", {}, "放在头版哪个板块？可以多选"),
      h("p", {}, "比如 ちいかわ 既是周边又有动画，就选「グッズ」和「映像」。版面只有一个，放在主板块；其他板块的目录里放一个「⇄ 乗換」的站，" +
                 "点了跳到同一个版面，同一条新闻不会出现两次。推荐的是按维基数据的说明、名字和你选的关注方面定的。"),
      h("div", {class: "opts secgrid", role: "group"}, SECS.map(x => h("button", {type: "button", class: "opt", "aria-pressed": String(chosen.includes(x.key)),
        onclick: () => toggle(x.key)}, x.ja, rec.has(x.key) ? h("small", {}, "推荐") : null))),
      main, nav(chosen.length > 0));
  }

  // 上级：同一系列 / 品牌 / IP 里的一部作品、一个商品（ちいかわ アニメ → ちいかわ）。只做一层，所以候补只有自己没有上级的。
  // 名字・维基数据里出现了的已有项排前面并推荐；其他的从下拉里选
  function askParent() {
    const cand = parentCandidates(), rest = tops().filter(i => !cand.includes(i));
    if (S.ans.parent == null) S.ans.parent = defaults("parent");
    const pick = v => { S.ans.parent = v; S.auto.parent = false; delete S.ans.subs;
                        S.ans.section = v ? (CFG.items.find(i => i.name === v) || {}).section : undefined; };
    const opts = [...cand.map(i => ({v: i.name, label: i.name, hint: `推荐 · 跟着它放在「${secOf(i.section).ja}」`})),
                  {v: "", label: "不属于任何一个", hint: "单独一个版面"}];
    const sel = h("select", {"aria-label": "从全部关注项里选上级", onchange: ev => { if (ev.target.value) { pick(ev.target.value); next(); } }},
      h("option", {value: ""}, "其他关注项…"), rest.map(i => h("option", {value: i.name, selected: S.ans.parent === i.name}, `${i.name}（${secOf(i.section).ja}）`)));
    return h("div", {class: "q"}, h("span", {class: "no"}, no()), h("h3", {}, `「${S.name}」属于哪个已有的关注项？`),
      h("p", {}, "同一个 IP、系列、品牌里的一部作品或一个商品，挂在它下面（比如「ちいかわ アニメ」挂在「ちいかわ」下面）。" +
                 "放在同一个板块，同一条新闻只出现在下级的版面。只做一层。"),
      h("div", {class: "opts", role: "radiogroup"}, opts.map(o => h("button", {type: "button", class: "opt", "aria-pressed": String(S.ans.parent === o.v),
        onclick: () => { pick(o.v); next(); }}, o.label, h("small", {}, o.hint)))),
      rest.length ? sel : null, nav(true));
  }

  // 小分类：板块的每种分法各选一个（sections.yaml 的常用值；放不进去就自己写，日语、短）
  function askSubs() {
    if (!S.ans.section) S.ans.section = guessSection();
    const sec = secOf(S.ans.section);
    if (S.ans.subs == null) S.ans.subs = defaults("subs");
    const subs = S.ans.subs;
    let okBtn;
    const done = () => (sec.schemes || []).every(sc => (subs[sc.id] || "").trim());
    const rows = (sec.schemes || []).map(sc => {
      const vals = (sc.values || []).map(vOf);
      const own = subs[sc.id] && !vals.includes(subs[sc.id]) ? subs[sc.id] : "";
      return h("div", {class: "subrow"}, h("h4", {}, sc.label),
        h("div", {class: "opts", role: "radiogroup", "aria-label": sc.label}, vals.map(v => h("button", {type: "button", class: "opt",
          "aria-pressed": String(subs[sc.id] === v), onclick: () => { subs[sc.id] = v; S.auto.subs = false; draw(); }}, v))),
        h("input", {type: "text", maxlength: 20, value: own, placeholder: "放不进去就自己写（日语、短）", "aria-label": `${sc.label}：自己写`,
          oninput: ev => { const t = ev.target.value.trim(); if (t) subs[sc.id] = t; else subs[sc.id] = vals[0]; S.auto.subs = false; okBtn.disabled = !done(); }}));
    });
    // 也放在的板块：各自的小分类（乗換の駅がその板块のどの小分類に並ぶか）
    const others = S.ans.parent ? [] : (S.ans.sections || []).filter(k => k !== S.ans.section);
    S.ans.also = Object.fromEntries(others.map(k => [k, S.ans.also?.[k] || alsoSubs(k)]));
    for (const k of others) {
      rows.push(h("h4", {class: "alsoh"}, `⇄「${secOf(k).ja}」里的小分类（乗換の站）`));
      for (const sc of secOf(k).schemes || []) {
        const vals = (sc.values || []).map(vOf), cur = S.ans.also[k];
        rows.push(h("div", {class: "subrow"}, h("h4", {}, sc.label),
          h("div", {class: "opts", role: "radiogroup", "aria-label": `${secOf(k).ja}・${sc.label}`}, uniq([...vals, cur[sc.id]]).map(v => h("button", {type: "button", class: "opt",
            "aria-pressed": String(cur[sc.id] === v), onclick: () => { cur[sc.id] = v; draw(); }}, v)))));
      }
    }
    const n = nav(done()); okBtn = n.querySelector(".main");
    return h("div", {class: "q"}, h("span", {class: "no"}, no()), h("h3", {}, `「${sec.ja}」里的小分类`),
      h("p", {}, "左边目录按它分组。每种分法各选一个，用哪种分法在本页上面的「目录的小分类分法」选。"), ...rows,
      h("div", {class: "opts"}, h("button", {type: "button", class: "opt auto", "aria-pressed": String(!!S.auto.subs),
        onclick: () => { S.ans.subs = guessSubs(S.ans.section); S.auto.subs = true; next(); }},
        "不确定，你帮我定", h("small", {}, `会选：${Object.values(guessSubs(S.ans.section)).join(" · ") || "—"}`))), n);
  }

  function multi(id, ask, hint, opts, {other, min = 0} = {}) {
    const body = [h("span", {class: "no"}, no()), h("h3", {}, ask), hint ? h("p", {}, hint) : null, options(id, opts, true)];
    let okBtn;
    const valid = () => (S.ans[id] || []).length + (other && S.ans[id + "_other"] ? 1 : 0) >= min;
    if (other) body.push(h("input", {type: "text", maxlength: 200, value: S.ans[id + "_other"] || "", placeholder: other,
      "aria-label": other, oninput: ev => { S.ans[id + "_other"] = ev.target.value.trim(); okBtn.disabled = !valid(); }}));
    const n = nav(valid()); okBtn = n.querySelector(".main");
    body.push(n);
    return h("div", {class: "q"}, ...body);
  }

  function text(id, ask, hint, placeholder) {
    const input = h("input", {type: "text", maxlength: 300, value: S.ans[id] || "", placeholder, "aria-label": ask,
      oninput: ev => { S.ans[id] = ev.target.value; }});
    return h("div", {class: "q"}, h("span", {class: "no"}, no()), h("h3", {}, ask), h("p", {}, hint), input, nav(true));
  }

  // ---------- 回答 → items.yaml 的字段 ----------
  const uniq = list => [...new Set(list.filter(x => x != null).map(x => String(x).trim()).filter(Boolean))];

  function build() {
    const pick = wdPick(), base = S.original || {}, names = pick?.names || {};
    const k = kindOf(), focus = chosenFocus();
    const players = uniq((S.ans.player || "").split(/[,，、\n]+/));
    const official = uniq([S.mode === "edit" ? (base.keywords || [])[0] || S.name : S.name,
                           names.zhHant, names.zhHans, names.ja, names.ko, names.en]);
    const extra = focus.flatMap(f => f.kw || []).map(t => t.replace("{n}", S.name).replace("{en}", names.en || S.name).replace("{ja}", names.ja || S.name));
    const keywords = S.mode === "edit" && !pick ? uniq([...(base.keywords || [S.name]), ...extra, ...players])
                                                : uniq([...official, ...extra, ...players]).slice(0, 12);
    const match = S.mode === "edit" && !pick ? uniq([...(base.match || base.keywords || [S.name]), ...players])
                                             : uniq([...official, ...(pick?.aliases || []), ...players]).slice(0, 30);
    const names4re = S.mode === "edit" && !pick ? uniq(base.match || base.keywords || [S.name]) : uniq([...official, ...(pick?.aliases || [])]);
    const alias = (players.length ? players : names4re.slice(0, 10)).map(esc).join("|");
    const urgentIds = (S.ans.urgent || []).includes("none") ? [] : S.ans.urgent || [];
    const urgent = focus.filter(f => f.urgent && urgentIds.includes(f.id)).map(f => `(${alias}).{0,30}${f.urgent}`);
    const exclude = uniq(EXCLUDES.filter(x => (S.ans.exclude || []).includes(x.id)).flatMap(x => x.words));
    const priority = uniq([...focus.map(f => f.id === "player" ? `${players.join("、")}的消息` : f.priority),
                           S.ans.focus_other || ""]).join("；");
    const parent = S.ans.parent ?? base.parent ?? "";
    const section = (parent && (CFG.items.find(i => i.name === parent) || {}).section) || S.ans.section || base.section || guessSection();
    const d = {
      ...base,
      type: k.type, parent, section, subs: S.ans.subs || base.subs || guessSubs(section),
      also: parent ? {} : S.ans.also || (S.ans.sections ? Object.fromEntries(S.ans.sections.filter(x => x !== section).map(x => [x, alsoSubs(x)])) : base.also || {}),
      keywords, match,
      // 修改时跳过了的问题保留原来的设置
      priority: focus.length || S.ans.focus_other ? priority : base.priority || "",
      urgent_patterns: S.ans.urgent ? urgent : base.urgent_patterns || [], exclude: uniq([...(S.mode === "edit" ? base.exclude || [] : []), ...exclude]),
      news_langs: S.ans.langs || defaults("langs"),
    };
    if (S.mode === "add") {
      d.size = S.ans.size || "M";
      d.notes = [`关注：${[...focus.map(f => f.label), S.ans.focus_other].filter(Boolean).join("、")}。`,
                 pick?.desc ? `维基数据：${pick.desc}。` : ""].join("");
    }
    if (pick) {
      const sub = names.ja && names.ja !== S.name ? names.ja : names.en && names.en !== S.name ? names.en : "";
      if (sub && !d.subtitle) d.subtitle = sub;
      if (pick.steam && !d.steam_appid) d.steam_appid = Number(pick.steam);
      if (pick.anilist && !d.anilist_id && S.ans.kind === "anime") d.anilist_id = Number(pick.anilist);
      else if (pick.anilistManga && !d.anilist_id && S.ans.kind === "anime") { d.anilist_id = Number(pick.anilistManga); d.anilist_type = "MANGA"; }
      if (pick.tmdb && !d.tmdb && S.ans.kind === "show") d.tmdb = pick.tmdb;
      if (pick.site && !d.site) d.site = pick.site;
    }
    return d;
  }

  // ---------- 汇总（最后一步；修改时直接从这里开始） ----------
  const FIELDS = [
    ["subtitle", "副标题", "板块标题旁的小字，如日文名", "text"],
    ["keywords", "搜索关键词", "每个词单独搜一次，一行一个；各语言的正式名称都写上", "lines"],
    ["match", "只留提到这些词的", "标题或摘要里至少有一个，否则丢掉，一行一个；不填就用搜索关键词", "lines"],
    ["priority", "最关心它的什么", "直接回答这个的新消息排最前面、做成大板块", "area"],
    ["exclude", "不想看的词", "标题里有这些词的直接丢掉，一行一个", "lines"],
  ];
  const ADVANCED = [
    ["urgent_patterns", "要紧消息规则", "标题命中这些正则的当天推 Discord，一行一条", "code"],
    ["steam_appid", "Steam 编号", "Steam 商店网址里的数字，用来抓公告和价格", "text"],
    ["anilist_id", "AniList 编号", "anilist.co 网址里的数字", "text"],
    ["anilist_type", "AniList 类型", "ANIME 或 MANGA", "text"],
    ["tmdb", "TMDB", "如 tv/1399 或 movie/693134", "text"],
    ["site", "官网", "用来找封面图", "text"],
    ["notes", "给 AI 编辑的背景说明", "读者是谁、已经知道什么、不报什么", "area"],
  ];

  function review() {
    const d = S.draft || build();
    S.draft = d;
    const field = ([key, name, hint, kind]) => {
      const v = d[key];
      const val = Array.isArray(v) ? v.join("\n") : v ?? "";
      const input = kind === "text" ? h("input", {type: "text", value: val, "data-k": key})
        : h("textarea", {"data-k": key, class: kind === "code" ? "code" : null, rows: kind === "area" ? 3 : Math.min(8, Math.max(3, String(val).split("\n").length))}, val);
      return h("label", {}, h("span", {}, name), h("small", {}, hint), input);
    };
    const types = h("select", {"data-k": "type"}, Object.entries(TYPES).map(([v, l]) => h("option", {value: v, selected: d.type === v}, l)));
    const section = h("select", {"data-k": "section", disabled: !!d.parent}, SECS.map(x => h("option", {value: x.key, selected: d.section === x.key}, x.ja)));
    const parentSel = h("select", {"data-k": "parent"}, h("option", {value: ""}, "不属于（单独一个版面）"),
      tops().map(i => h("option", {value: i.name, selected: d.parent === i.name}, `${i.name}（${secOf(i.section).ja}）`)));
    parentSel.addEventListener("change", () => {   // 上级を選んだら板块は上級と同じ（変えられない）
      const p = (CFG.items || []).find(i => i.name === parentSel.value);
      section.disabled = !!p;
      if (p) { section.value = p.section; drawSubs(p.section); }
    });
    // 小分类：分法ごとに 1 つ（常用值から選ぶ。放不进去的自己写った値も残す）。板块を変えたら作り直す
    const subsBox = h("div", {class: "two subs"});
    const drawSubs = key => {
      const cur = key === d.section ? d.subs || {} : guessSubs(key);
      subsBox.replaceChildren(...(secOf(key).schemes || []).map(sc => {
        const vals = uniq([...(sc.values || []).map(vOf), cur[sc.id]]);
        return h("label", {}, h("span", {}, `小分类・${sc.label}`),
          h("select", {"data-sub": sc.id}, vals.map(v => h("option", {value: v, selected: cur[sc.id] === v}, v))));
      }));
    };
    // 也放在（乗換の駅）：板块ごとにチェック、チェックした板块の小分類
    const alsoBox = h("div", {class: "alsobox"});
    const drawAlso = () => {
      const main = section.value, cur = d.also || {};
      alsoBox.replaceChildren(h("span", {}, "也放在（目录里放 ⇄ 乗換的站，版面只有一个）"),
        h("div", {class: "checks"}, SECS.filter(x => x.key !== main).map(x => h("label", {}, h("input", {type: "checkbox", value: x.key,
          checked: !!cur[x.key], "data-also": "", onchange: ev => { if (ev.target.checked) cur[x.key] = cur[x.key] || alsoSubs(x.key); else delete cur[x.key]; d.also = cur; drawAlso(); }}), x.ja))),
        ...Object.keys(cur).filter(k => k !== main).map(k => h("div", {class: "two subs"}, (secOf(k).schemes || []).map(sc =>
          h("label", {}, h("span", {}, `⇄ ${secOf(k).ja}・${sc.label}`),
            h("select", {"data-also-sub": `${k}|${sc.id}`}, uniq([...(sc.values || []).map(vOf), cur[k][sc.id]]).map(v => h("option", {value: v, selected: cur[k][sc.id] === v}, v))))))));
    };
    drawSubs(d.section);
    drawAlso();
    section.addEventListener("change", () => { drawSubs(section.value); drawAlso(); });
    const langs = h("div", {class: "checks"}, Object.entries(LANGS).map(([v, l]) =>
      h("label", {}, h("input", {type: "checkbox", value: v, checked: (d.news_langs || []).includes(v), "data-lang": ""}), l)));
    const size = S.mode === "add" ? h("div", {class: "f"}, h("span", {}, "篇幅"), h("div", {class: "checks"}, ["S", "M", "L"].map(v =>
      h("label", {}, h("input", {type: "radio", name: "wl-size", value: v, checked: d.size === v}), v)))) : null;
    const msg = h("span", {class: "msg", role: "status"});
    const send = h("button", {type: "button", class: "main", onclick: () => submit(form, msg, send)}, S.mode === "edit" ? "提交修改" : "提交");
    const form = h("div", {class: "rv"},
      S.mode === "add" ? h("label", {}, h("span", {}, "名字"), h("small", {}, "简报上显示的名字"),
        h("input", {type: "text", value: S.name, maxlength: 80, "data-k": "name"})) : null,
      h("div", {class: "two"}, h("label", {}, h("span", {}, "类型"), types),
        h("label", {}, h("span", {}, "板块"), section)),
      d.parent ? null : alsoBox,
      tops().length ? h("label", {}, h("span", {}, "上级"), h("small", {}, "同一个 IP・系列・品牌里的作品或商品，挂在它下面；板块跟着上级"), parentSel) : null,
      subsBox,
      size,
      FIELDS.map(field),
      h("div", {class: "f"}, h("span", {}, "新闻语言"), langs),
      h("details", {open: S.mode === "edit" ? null : null}, h("summary", {}, "高级：要紧消息规则、编号、官网、背景说明"),
        h("div", {class: "rv"}, ADVANCED.map(field))));
    return h("div", {class: "q"},
      h("span", {class: "no"}, S.mode === "edit" ? "现在的设置" : "最后一步：看一眼"),
      h("h3", {}, S.mode === "edit" ? `「${S.name}」现在是这样` : "按你的回答，会这样加进关注清单"),
      h("p", {}, S.mode === "edit" ? `直接改下面的内容，或者「重新问一遍」按问题重新设置。提交后${eta()}生效，下面会显示进度。`
                                   : `都可以直接改。提交后${eta()}加进关注清单，接着马上收集新闻（往前补抓 6 周），Discord 会收到通知；下面会显示进度。`),
      form,
      h("div", {class: "wnav"},
        S.mode === "add" ? h("button", {type: "button", onclick: back}, "← 上一步")
                         : h("button", {type: "button", onclick: () => { S.step = 0; S.ans = {}; draw(); }}, "重新问一遍"),
        send, h("button", {type: "button", onclick: reset}, "取消"), msg));
  }

  function readForm(form) {
    const d = {...S.draft};
    form.querySelectorAll("[data-k]").forEach(el => {
      const k = el.dataset.k, v = el.value.trim();
      if (k === "name") return;
      const isList = ["keywords", "match", "exclude", "urgent_patterns"].includes(k);
      d[k] = isList ? uniq(v.split("\n")) : v;
    });
    d.subs = Object.fromEntries([...form.querySelectorAll("[data-sub]")].map(el => [el.dataset.sub, el.value]));
    const also = {};
    if (!d.parent) {
      for (const el of form.querySelectorAll("[data-also]:checked")) if (el.value !== d.section) also[el.value] = {};
      for (const el of form.querySelectorAll("[data-also-sub]")) { const [k, id] = el.dataset.alsoSub.split("|"); if (also[k]) also[k][id] = el.value; }
    }
    d.also = also;
    d.news_langs = [...form.querySelectorAll("[data-lang]:checked")].map(x => x.value);
    const size = form.querySelector("input[name=wl-size]:checked");
    if (size) d.size = size.value;
    for (const k of ["steam_appid", "anilist_id"]) if (/^\d+$/.test(d[k] ?? "")) d[k] = Number(d[k]);
    return d;
  }

  function problems(d, name) {
    if (!name) return "名字要填";
    if (!d.section) return "板块要选";
    if ((secOf(d.section).schemes || []).some(sc => !(d.subs || {})[sc.id])) return "小分类每种分法都要选";
    for (const [k, v] of Object.entries(d.also || {})) if ((secOf(k).schemes || []).some(sc => !v[sc.id])) return `「${secOf(k).ja}」的小分类每种分法都要选`;
    if (!d.news_langs.length) return "至少选一种新闻语言";
    for (const p of d.urgent_patterns || []) { try { new RegExp(p); } catch (_) { return `要紧消息规则写错了：${p.slice(0, 30)}…`; } }
    for (const k of ["steam_appid", "anilist_id"]) if (d[k] !== "" && d[k] != null && !Number.isInteger(d[k])) return `${k} 要是数字`;
    if (d.tmdb && !/^(tv|movie)\/\d+$/.test(d.tmdb)) return "TMDB 要写成 tv/1399 或 movie/693134";
    if (d.site && !/^https?:\/\/\S+$/.test(d.site)) return "官网要是 http(s) 网址";
    if (d.anilist_type && !["ANIME", "MANGA"].includes(d.anilist_type)) return "AniList 类型只能是 ANIME 或 MANGA";
    return "";
  }

  const norm = (k, v) => Array.isArray(v) ? (k === "news_langs" ? [...v].sort() : v) : v ?? "";
  const same = (k, a, b) => JSON.stringify(norm(k, a ?? (Array.isArray(b) ? [] : ""))) === JSON.stringify(norm(k, b ?? (Array.isArray(a) ? [] : "")));
  const KEYS = ["type", "parent", "section", "subs", "also", "size", "subtitle", "keywords", "match", "exclude", "news_langs", "priority", "urgent_patterns",
                "site", "steam_appid", "anilist_id", "anilist_type", "tmdb", "notes"];

  async function submit(form, msg, btn) {
    const d = readForm(form);
    const name = S.mode === "add" ? form.querySelector("[data-k=name]").value.trim() : S.name;
    const bad = problems(d, name);
    const sayMsg = (t, cls) => { msg.textContent = t; msg.className = "msg " + (cls || ""); };
    if (bad) { sayMsg(bad, "err"); return; }
    if (S.mode === "add" && CFG.items.some(i => i.name === name)) { sayMsg(`关注清单里已经有「${name}」了，在上面的列表里点「改」`, "err"); return; }
    const config = {};
    for (const k of KEYS) {
      if (S.mode === "edit") { if (!same(k, d[k], S.original[k])) config[k] = d[k] ?? null; }
      else if (d[k] != null && d[k] !== "" && !(Array.isArray(d[k]) && !d[k].length)) config[k] = d[k];
    }
    if (S.mode === "edit" && !Object.keys(config).length) { sayMsg("没有改动", "err"); return; }
    btn.disabled = true; sayMsg("提交中…");
    try {
      const r = await fetch(`${CFG.url}/rest/v1/rpc/submit_item`, {method: "POST",
        headers: {apikey: CFG.key, "Content-Type": "application/json"},
        body: JSON.stringify({p_action: S.mode, p_name: name, p_config: config})});
      if (r.ok) {
        const what = S.mode === "edit" ? `已提交「${name}」的修改 ✓ 进度看下面「最近提交的」，会自动刷新`
                                       : `已提交「${name}」✓ 进度看下面「最近提交的」，会自动刷新`;
        reset(); loadQueue();
        const note = box.querySelector(".hint, .q p"); if (note) { note.textContent = what; note.className = "msg ok"; }
        return;
      }
      const err = await r.json().catch(() => ({}));
      sayMsg("没存上：" + (err.message || r.status), "err");
    } catch (_) { sayMsg("连不上数据库", "err"); }
    btn.disabled = false;
  }

  // ---------- 最近提交的（进度，有没处理完的就每 15 秒刷新一次） ----------
  // 一提交数据库就立刻叫 GitHub 的「网页请求」工作流（事件触发）：处理完标成 done，新增的马上开始收集新闻
  const queueList = h("ul", {class: "queue", "aria-label": "最近提交的，自动刷新"});
  const ago = t => { const m = Math.max(0, Math.round((Date.now() - new Date(t)) / 60000)); return m < 1 ? "刚刚" : m < 60 ? `${m} 分钟前` : `${Math.round(m / 60)} 小时前`; };
  const progress = x => {
    if (x.status === "skipped") return ["err", `没处理：${x.note || "内容不对"}`];
    if (x.status === "done") return ["ok", x.action === "edit" ? "✓ 已改好，网页 1 分钟内更新（刷新本页就能看到）"
                                                            : "✓ 已加进关注清单，首页已经有它的版面，新闻收集完（几分钟）就会出现"];
    const m = (Date.now() - new Date(x.created_at)) / 60000;
    if (!INSTANT) return ["wait", "已收到 ✓ 还没设 GitHub 令牌，下次每 2 小时的更新时处理"];
    return ["wait", m < 5 ? "已收到 ✓ 已经叫 GitHub 马上处理，网页正在重新生成"
                          : "已收到 ✓ GitHub 这次有点慢，还在处理"];
  };
  let timer = null;
  // 数据库里设了 GitHub 令牌（db/instant.sql）时，提交后立刻叫 GitHub 处理；没设就等每 2 小时的更新
  let INSTANT = false;
  const eta = () => INSTANT ? "马上" : "下次更新时（最多 2 小时）";
  function loadQueue() {
    if (!CFG.url || !CFG.key) return;
    fetch(`${CFG.url}/rest/v1/rpc/list_item_requests`, {method: "POST", headers: {apikey: CFG.key, "Content-Type": "application/json"}, body: "{}"})
      .then(r => r.ok ? r.json() : []).then(list => {
        list = list || [];
        queueList.replaceChildren(...(list.length ? [h("li", {class: "qh"}, "最近提交的（自动刷新）")] : []), ...list.map(x => {
          const [cls, text] = progress(x);
          return h("li", {}, h("b", {}, x.name), h("span", {}, ` · ${x.action === "edit" ? "修改" : "新增"} · ${ago(x.created_at)}`),
            h("strong", {class: "st-" + cls}, text));
        }));
        clearTimeout(timer);
        if (list.some(x => x.status === "pending")) timer = setTimeout(loadQueue, 15000);
      }).catch(() => { clearTimeout(timer); timer = setTimeout(loadQueue, 30000); });
  }

  // ---------- 入口 ----------
  function reset() { S = fresh(); draw(); }

  window.wlEditItem = name => {
    const item = CFG.items.find(i => i.name === name);
    if (!item) return;
    S = fresh();
    S.mode = "edit"; S.name = name; S.original = {...item, news_langs: item.news_langs || CFG.langs};
    S.ans = {kind: KIND_OF_TYPE[item.type] || "product", section: item.section, parent: item.parent || "", subs: item.subs ? {...item.subs} : undefined, langs: item.news_langs,
             sections: [item.section, ...Object.keys(item.also || {})], also: item.also ? JSON.parse(JSON.stringify(item.also)) : undefined};
    if (item.section === "运动" && item.type === "category") S.ans.kind = "sports";
    S.draft = {...S.original};
    S.step = live().length - 1;
    draw();
    box.scrollIntoView({behavior: "smooth", block: "start"});
  };

  if (!CFG.url || !CFG.key) {
    box.replaceChildren(h("h2", {}, "＋ 新增关注项"), h("p", {class: "hint"}, "还没连数据库（items.yaml 的 supabase_url / supabase_key），暂时只能跟 Claude 说。"));
    return;
  }
  reset();
  loadQueue();
  fetch(`${CFG.url}/rest/v1/rpc/instant_enabled`, {method: "POST", headers: {apikey: CFG.key, "Content-Type": "application/json"}, body: "{}"})
    .then(r => r.ok ? r.json() : false).then(on => {
      INSTANT = on === true;
      const el = document.getElementById("wl-eta");
      if (el && INSTANT) el.textContent = "马上叫 GitHub 更新网页";
      if (INSTANT) loadQueue();
    }).catch(() => {});
})();
