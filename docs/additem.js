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

  // 每种东西可以关注的方面。sec = 选了它就推荐「也放在」这个板块（[板块, 小分类的预设]，ちいかわ选「动画」→ 作品・アニメ）。
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
      {sec: ["好物", {kind: "キャラグッズ", owner: "キャラクター"}], id: "collab", label: "联名、周边", hint: "跨界联动、手办、周边", priority: "联名和周边",
       urgent: "(コラボ|联名|聯名|collab|グッズ|周边|周邊|フィギュア)"},
      {id: "story", label: "剧情、角色、世界观", hint: "新剧情、角色设定", priority: "新剧情和角色设定"},
    ]},
    anime: {label: "动画 / 漫画", hint: "番剧、漫画、轻小说", type: "anime", section: "影视", focus: [
      {rec: true, id: "sequel", label: "新一季 / 续作 / 剧场版", hint: "什么时候官宣、定档", priority: "新一季、续作或剧场版什么时候出",
       urgent: "(第\\s?[0-9一二三四五六七八九十]+\\s?(季|期)|続編|续篇|續篇|新作|劇場版|剧场版|映画化|放送決定|定档|定檔|製作決定|制作决定|season \\d|sequel)"},
      {rec: true, id: "air", label: "播出时间、每集更新", hint: "什么时候播、在哪看", priority: "播出时间和每集更新"},
      {sec: ["影视", {kind: "マンガ"}], id: "manga", label: "漫画连载、单行本", hint: "最新话、出刊、完结", priority: "漫画连载和单行本",
       urgent: "(単行本|单行本|最新刊|最終回|最终话|最終話|完結|完结|休載|休刊)"},
      {sec: ["好物", {kind: "キャラグッズ", owner: "キャラクター"}], id: "collab", label: "周边、联名、展览", hint: "快闪店、联名商品", priority: "周边、联名和展览",
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
    book: {label: "书 / 杂志 / 漫画单行本", hint: "杂志、小说、漫画、写真集", type: "product", section: "影视", focus: [
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
    food: {label: "吃的 / 喝的", hint: "咖啡店、甜点、餐厅、零食", type: "product", section: "生活", focus: [
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
  const SECS_BY_PRIO = [...SECS].sort((a, b) => (a.prio ?? 50) - (b.prio ?? 50));   // 对号入座的顺序（ゲーム先看）
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
    const hit = SECS_BY_PRIO.find(x => { const re = secRe(x); return re && re.test(t); });
    return hit ? hit.key : kindOf().section;
  }
  // 有上级就跟着上级的板块（目录上挂在上级下面），没有就是它自己本来的板块
  const parentItem = () => S.ans.parent ? (CFG.items || []).find(i => i.name === S.ans.parent) : null;
  const guessSection = () => parentItem()?.section || naturalSection();
  // 上级候补：已有的、自己没有上级的关注项里，名字或搜索词出现在新项的名字・维基数据里的（「ちいかわ 映像」→ ちいかわ）
  const tops = () => (CFG.items || []).filter(i => !i.parent && i.name !== S.name);
  function parentCandidates() {
    const t = context().toLowerCase();
    const bySeries = seriesOfPick().map(seriesItem).filter(Boolean);   // 维基数据说它属于这个系列（已经在关注清单里）
    return [...new Set([...bySeries, ...tops().filter(i => [i.name, ...(i.keywords || [])].some(w => w && w.length >= 2 && t.includes(String(w).toLowerCase())))])];
  }
  // 每种分法选一个值：说明・名字里出现了的，没有就第一个
  function guessSubs(key, extra = "") {
    const t = context() + " " + extra, out = {};
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
      const pick = (S.ans.kind === "character" ? vals.find(v => /^キャラ/.test(vOf(v))) : null) ?? vals.find(v => says(v, t)) ?? vals[0];
      if (pick != null) out[sc.id] = vOf(pick);
    }
    return out;
  }

  // 「也放在」的推荐：选了的关注方面带 sec 的板块（ちいかわ：选「动画、电影、活动」→ 作品）。主板块（版面所在）除外
  const alsoRec = main => [...new Set(chosenFocus().filter(f => f.sec && f.sec[0] !== main).map(f => f.sec[0]))];
  const secsNow = () => S.ans.sections || [S.ans.section || guessSection(), ...alsoRec(S.ans.section || guessSection())];
  // 也放在的板块里的小分类：按关注方面的预设，其他按说明・名字
  function alsoSubs(key) {
    const pre = chosenFocus().find(f => f.sec && f.sec[0] === key)?.sec[1] || {};
    const base = guessSubs(key);
    return Object.fromEntries((secOf(key).schemes || []).map(sc => [sc.id, pre[sc.id] || base[sc.id]]));
  }

  // ---------- 「面」：输入一个名字，列出它有哪几面（动画・电影・周边…… / 猫：用品・フード・健康……），全部让你勾 ----------
  // 作品・IP 型：下面的媒体面全部列出；维基数据里同名的条目（「映画ちいかわ」「Spider-Verse」）・编号（AniList / TMDB / Steam）・说明里的词
  //   找到依据的默认勾上并写出依据，具体作品名也变成关键词。
  // 题材型（「猫」这种普通词）：它的板块在 sections.yaml 写的 facets 全部列出（rec 的默认勾上）。名字太泛，每个面用「名字＋面的词」同时出现才收。
  // 每个面 = 一套关键词 ＋ 一个板块。勾了几个就放进几个板块（版面一个＋乗換駅，或者每个面一个版面）。都是规则，不用 AI。
  const MEDIA = {
    goods: {label: "グッズ・コラボ", hint: "联名、周边、一番赏、快闪店", kind: "character", sec: "好物", subs: {kind: "キャラグッズ", owner: "キャラクター"},
            kw: ["コラボ", "グッズ 新作", "一番くじ", "ポップアップ"], re: "コラボ|グッズ|一番くじ|ポップアップ|フェア|POP ?UP|联名|聯名|周边|周邊|merch|collab|figure|フィギュア",
            tail: "グッズ", hit: /キャラクター|character|mascot|マスコット|角色|吉祥物/i},
    anime: {label: "アニメ", hint: "电视动画、配信、声优", kind: "anime", sec: "影视", subs: {kind: "アニメ"},
            kw: ["アニメ", "アニメ 放送"], re: "アニメ|anime|動畫|动画|放送|配信|animated series", tail: "アニメ",
            hit: /アニメ|anime|animated (television|TV|series)|动画|動畫/i},
    movie: {label: "映画", hint: "剧场版、电影：定档、预告、票房", kind: "show", sec: "影视", subs: {kind: "映画"},
            kw: ["映画", "劇場版"], re: "映画|劇場版|剧场版|電影|电影|movie|film|box office|興行", tail: "映画",
            hit: /映画|劇場|film|movie|电影|電影/i},
    drama: {label: "ドラマ・実写", hint: "电视剧、网剧、实写版", kind: "show", sec: "影视", subs: {kind: "ドラマ"},
            kw: ["ドラマ", "実写"], re: "ドラマ|実写|drama|series|电视剧|電視劇|剧集|劇集", tail: "ドラマ",
            hit: /ドラマ|television (drama|series)|TV series|电视剧|電視劇|剧集/i},
    manga: {label: "漫画・本", hint: "连载、单行本、画集", kind: "book", sec: "影视", subs: {kind: "マンガ"},
            kw: ["単行本", "最新刊"], re: "漫画|漫畫|マンガ|manga|comic|単行本|单行本|最新刊|連載|连载|画集", tail: "漫画",
            hit: /漫画|漫畫|マンガ|manga|comic/i},
    game: {label: "ゲーム", hint: "游戏、手游的新作和更新", kind: "game", sec: "游戏", subs: {},
           kw: ["ゲーム", "game"], re: "ゲーム|game|游戏|遊戲|アプリ|Switch|PS5|Steam", tail: "ゲーム",
           hit: /ゲーム|video game|游戏|遊戲/i},
    // 联名咖啡・展览・快闪店 = 出かけて行くもの → おでかけ・アート（2026-10-19 用户的树状图）。舞台・ミュージカル・演唱会は音楽・ライブ
    event: {label: "イベント・カフェ・展示", hint: "联名咖啡、展览、快闪店", kind: "place", sec: "出行", subs: {kind: "季節イベント"},
            kw: ["コラボカフェ", "展", "ポップアップ"], re: "コラボカフェ|カフェ|展覧会|展示|ポップアップ|POP ?UP|イベント|フェア|展", tail: "イベント",
            hit: /exhibition|展覧会|展示会|テーマパーク|theme park|attraction/i},
    live: {label: "舞台・ライブ", hint: "舞台、音乐剧、演唱会", kind: "artist", sec: "演出", subs: {scene: "舞台・ミュージカル", form: "舞台"},
           kw: ["舞台", "ミュージカル"], re: "ライブ|舞台|ミュージカル|コンサート|concert|musical|stage", tail: "舞台",
           hit: /ミュージカル|musical|舞台|stage|concert|ライブ/i},
  };
  const normName = t => String(t || "").toLowerCase().replace(/[\s・:：!！?？\-–—.,'"「」『』()（）]/g, "");
  // 维基数据里和这个名字有关的条目（标题・别名里含有这个名字，或名字含有它）
  function relatedHits() {
    const n = normName(S.name);
    if (!n) return [];
    return (S.wd || []).filter(x => [x.title, ...Object.values(x.names || {}), ...(x.aliases || [])].some(t => {
      const m = normName(t); return m && (m.includes(n) || (m.length >= 2 && n.includes(m)));
    }));
  }
  // 名字本身（各语言）：搜索词的组合用（スパイダーマン コラボ・Spider-Man collab）
  const relatedNames = () => uniq([S.name, ...Object.values(wdPick()?.names || {})]).map(normName);
  // 作品・IP 型：每个媒体面找到的依据（条目）
  function mediaEvidence() {
    const ev = {};
    for (const x of relatedHits()) {
      const text = `${x.title} ${Object.values(x.names || {}).join(" ")} ${x.desc}`;
      const got = new Set(Object.entries(MEDIA).filter(([, f]) => f.hit.test(text)).map(([k]) => k));
      // 同じ条目の中の順：映画（アニメ映画も映画）＞ アニメ（「TV series」でもアニメならドラマにしない）＞ ドラマ
      if (got.has("movie")) { got.delete("anime"); got.delete("drama"); }
      if (got.has("anime")) got.delete("drama");
      if (x.anilist) got.add("anime");
      if (x.anilistManga) got.add("manga");
      if (x.tmdb?.startsWith("movie/")) got.add("movie");
      if (x.tmdb?.startsWith("tv/")) got.add(x.kind === "anime" ? "anime" : "drama");
      if (x.steam) got.add("game");
      if (x.kind === "character") got.add("goods");
      for (const k of got) (ev[k] = ev[k] || []).push(x);
    }
    // アニメ・漫画・映画・ゲームのうち 2 つ以上ある作品（ちいかわ）はグッズ・コラボもまず出ている → 推荐（依据は見つかった面）
    const media = ["anime", "manga", "movie", "game"].filter(k => ev[k]);
    if (!ev.goods && media.length >= 2) ev.goods = [{title: `${media.map(k => MEDIA[k].label).join("・")}がある作品`, desc: "", names: {}}];
    return ev;
  }
  // 名字是普通词吗（「猫」「犬」「咖啡」）：短的普通词，或维基数据说是动物・食物・概念这类
  const generic = () => normName(S.name).length <= 2 || /動物|动物|animal|species|食べ物|食物|food|概念|concept|スポーツ|sport|飲み物|beverage/i.test(wdPick()?.desc || "");
  // 这个名字的「面」一览。type = media（作品・IP）/ topic（题材）/ ""（只有一面，照普通的流程）
  function facetPlan() {
    if (S._plan && S._plan.key === S.name + "|" + (S.ans.which ?? "") + "|" + (S.wd || []).length) return S._plan;
    const ev = mediaEvidence(), key = S.name + "|" + (S.ans.which ?? "") + "|" + (S.wd || []).length;
    let plan = {key, type: "", list: []};
    const isChar = (S.ans.kind || wdPick()?.kind) === "character" || !!ev.goods;
    if (Object.keys(ev).length >= 1 && (Object.keys(ev).length >= 2 || isChar || ["anime", "manga", "movie"].some(k => ev[k]))) {
      plan = {key, type: "media", list: Object.entries(MEDIA).map(([k, f]) => ({key: k, ...f, rec: !!ev[k], ev: ev[k] || [],
        titles: uniq((ev[k] || []).flatMap(x => [x.names?.ja, x.names?.en]).map(t => String(t || "").replace(/\s*[(（][^)）]*[)）]\s*$/, "").trim())
          .filter(t => t && !relatedNames().includes(normName(t)))).slice(0, 4)}))};
    } else if (generic()) {
      const ns = secOf(naturalSection()), first = (ns.schemes || [])[0];   // 板块の第一の分け方の値（ペット・グルメ…）で面を選ぶ
      const kv = first ? guessSubs(ns.key)[first.id] : null;
      plan = {key, type: "topic", list: ((ns.facets || {})[kv] || ns.facets_any || []).map(f => ({key: f.id, ...f, kind: secOf(f.sec).kind,
        hint: `${secOf(f.sec).ja} · ${(f.kw || []).map(w => `${S.name} ${w}`).slice(0, 2).join(" / ")}`, ev: []}))};
    }
    S._plan = plan;
    return plan;
  }
  const facetOf = k => facetPlan().list.find(f => f.key === k);
  const chosenFacets = () => (S.ans.facets || []).map(facetOf).filter(Boolean);
  // 面的小分类：面的预设，其他按说明・名字（那个板块的每种分法都写）
  function facetSubs(f) {   // 判断地域等用：这个面的条目＋所有同名条目的说明（「美国电影」→ 海外）
    const base = guessSubs(f.sec, [...(f.ev || []), ...relatedHits()].map(x => `${x.title} ${x.desc || ""}`).join(" "));
    return Object.fromEntries((secOf(f.sec).schemes || []).map(sc => [sc.id, (f.subs || {})[sc.id] || base[sc.id]]));
  }
  // 主面（版面放的地方）：周边（角色 IP 的本体）→ アニメ → 漫画 → ゲーム → 映画 → 其他按勾的顺序
  const MAIN_ORDER = ["goods", "anime", "manga", "game", "movie", "drama", "live", "event"];
  // 一个题材可以放进几个板块，但同一个板块里只有一个版面（用户定的）：同一个板块的面合成一个版面，按「派生」归到一起——
  // 原作（漫画）→ アニメ → ドラマ・実写 → 映画（剧场版是动画・剧的派生），版面名用最「元」的面（ちいかわ アニメ 里也收映画）
  const DERIVE = ["goods", "manga", "anime", "drama", "movie", "game", "live", "event"];
  function facetGroups() {   // {板块: [面…]}（派生の順）
    const g = {};
    for (const f of chosenFacets()) (g[f.sec] = g[f.sec] || []).push(f);
    const at = f => (DERIVE.indexOf(f.key) + 1) || 99;
    for (const k in g) g[k].sort((a, b) => at(a) - at(b));
    return g;
  }
  const multiSec = () => Object.keys(facetGroups()).length >= 2;
  // 主面：面がいちばん多い板块（ちいかわ：作品に漫画・アニメ・映画 → 作品の「シリーズ」が主項）。同じ数なら MAIN_ORDER
  const mainFacet = () => {
    const fs = S.ans.facets || [];
    if (fs.includes(S.ans.mainFacet)) return S.ans.mainFacet;
    const rank = k => (MAIN_ORDER.indexOf(k) + 1) || 99;
    const best = Object.values(facetGroups()).sort((a, b) => b.length - a.length || rank(a[0].key) - rank(b[0].key))[0];
    return best?.[0]?.key || MAIN_ORDER.find(k => fs.includes(k)) || fs[0];
  };
  // 方法 4（用户定的）：同じ板块に 2 つ以上の媒体がある作品は小分類「シリーズ」（その板块の第一の分け方にシリーズがあるとき）
  function withSeries(sec, subs, n) {
    const first = (secOf(sec).schemes || [])[0];
    return n >= 2 && first && (first.values || []).map(vOf).includes("シリーズ") ? {...subs, [first.id]: "シリーズ"} : subs;
  }
  // 勾的面 → 板块・小分类・也放在（合成一个版面）；分开时主项只放主面
  function applyFacets() {
    const fs = chosenFacets();
    if (!fs.length) return;
    const main = facetOf(mainFacet());
    S.ans.mainFacet = main.key;
    if (!multiSec()) S.ans.arrange = "merge";   // 全部同じ板块 = 1 つの版面
    if (facetPlan().type === "media") S.ans.kind = main.kind;
    S.ans.section = main.sec;
    // 1 つの版面にまとめる：全部の面の数、板块ごと：主面の板块の面の数で「シリーズ」か決める
    S.ans.subs = withSeries(main.sec, facetSubs(main), S.ans.arrange === "split" ? fs.filter(f => f.sec === main.sec).length : fs.length);
    const also = {};
    if (S.ans.arrange !== "split") for (const f of fs) if (f.sec !== main.sec && !also[f.sec]) also[f.sec] = facetSubs(f);
    S.ans.also = also;
    S.ans.sections = [main.sec, ...Object.keys(also)];
    S.ans.parent = S.ans.parent || "";
  }
  // 已经有的相近的关注项（「猫」→ 猫用品、「蜘蛛侠」→ 漫威电影 是上级候补，在「属于哪个」一问里推荐）
  const similarItems = () => {
    const n = normName(S.name);
    return (CFG.items || []).filter(i => { const m = normName(i.name); return n && m && m !== n && (m.includes(n) || n.includes(m)); });
  };

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
    const bySec = SECS_BY_PRIO.find(x => { const re = secRe(x); return re && re.test(d); });
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
      // 属于哪个系列：系列（P179）・媒体系列（P8345）・是…的一部分（P361）。名字在 seriesLookup 里另外查
      seriesIds: [...new Set([...claim(ent, "P179"), ...claim(ent, "P8345"), ...claim(ent, "P361")].map(v => v.id).filter(Boolean))].slice(0, 3),
    };
  }

  // ---------- 状态 ----------
  let S;   // {mode, name, step, ans: {...}, wd, wdState, original, draft}
  const fresh = () => ({mode: "add", name: "", step: 0, ans: {}, auto: {}, wd: null, wdState: "idle", draft: null, original: null});

  const kindOf = () => KINDS[S.ans.kind] || KINDS.product;
  // 关注哪方面：作品・IP 型勾了几个面，就把每个面（アニメ・映画・グッズ……）的选项都列出来（id 前加面，如 anime.sequel）
  const focusOpts = () => {
    const fs = S.ans.facets?.length && facetPlan().type === "media" ? chosenFacets() : [];
    if (fs.length) return fs.flatMap(f => (KINDS[f.kind]?.focus || []).filter(o => !o.when || o.when())
      .map(o => ({...o, id: `${f.key}.${o.id}`, facet: f.key, sec: null, hint: `${f.label} · ${o.hint || ""}`})));
    return kindOf().focus.filter(f => !f.when || f.when());
  };
  const chosenFocus = () => focusOpts().filter(f => (S.ans.focus || []).includes(f.id));
  const wdPick = () => (S.wd || []).find(x => x.id === S.ans.which) || null;

  // 问题清单（add 模式从第 0 问开始；edit 模式「重新问一遍」从 kind 开始）
  const STEPS = [
    {id: "name", when: () => S.mode === "add", render: askName},
    {id: "which", when: () => S.mode === "add" && S.wdState !== "off", render: askWhich},
    {id: "facets", when: () => S.mode === "add" && facetPlan().type !== "", render: askFacets},
    {id: "arrange", when: () => S.mode === "add" && multiSec(), render: askArrange},
    {id: "kind", when: () => !(S.ans.facets || []).length || facetPlan().type === "topic", render: () => single("kind", "这是什么？", guessHint(),
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
    {id: "parent", when: () => (tops().length > 0 || newSeries().length > 0) && S.ans.arrange !== "split", render: askParent},
    {id: "section", when: () => !S.ans.parent && !(S.ans.facets || []).length, render: askSections},
    {id: "subs", render: askSubs},
    {id: "size", when: () => S.mode === "add", render: () => single("size", "每期给它多大篇幅？", "以后在上面的列表里随时能改。", [
      {v: "S", label: "S · 少", hint: "每期最多 3 条，大约一行"}, {v: "M", label: "M · 中等", hint: "每期最多 5 条"},
      {v: "L", label: "L · 多", hint: "每期最多 8 条，满满一整屏"}])},
    {id: "review", render: review},
  ];
  const live = () => STEPS.filter(s => !s.when || s.when());
  const LABELS = {name: "名字", which: "是哪个", facets: "关注的面", arrange: "怎么放", kind: "这是", focus: "关注", player: "选手 / 队伍", urgent: "立刻通知",
                  exclude: "不看", langs: "语言", parent: "上级", section: "板块", subs: "小分类", size: "篇幅"};

  function defaults(id) {
    const pick = wdPick();
    if (id === "kind") return pick?.kind || (S.original ? KIND_OF_TYPE[S.original.type] : "") || "";
    if (id === "urgent") return chosenFocus().filter(f => f.urgent).map(f => f.id);
    if (id === "langs") return [...new Set(["zh-TW", "en-US", ...(pick?.origin || []).filter(l => l !== "zh-CN")])];
    if (id === "section") return S.ans.parent ? guessSection() : S.original?.section || guessSection();
    if (id === "sections") return S.original ? [S.original.section, ...Object.keys(S.original.also || {})] : secsNow();
    if (id === "parent") return S.original ? S.original.parent || "" : parentCandidates()[0]?.name || "";
    if (id === "facets") return facetPlan().list.filter(f => f.rec).map(f => f.key);
    if (id === "arrange") return multiSec() ? "split" : "merge";
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
    if (id === "facets") return (v || []).map(k => facetOf(k)?.label).join("、") || "—";
    if (id === "arrange") return v === "split" ? "每个面一个版面" : "合成一个版面";
    if (id === "subs") return Object.values(v || {}).join(" · ");
    return v || "";
  }
  const AUTO_STEPS = ["which", "facets", "arrange", "kind", "focus", "urgent", "exclude", "langs", "parent", "section", "subs", "size"];
  function autoRest() {   // 「剩下的都交给你」：从这一问开始，没回答的都替你选，直接到汇总
    for (let i = S.step, steps = live(); i < steps.length; i++, steps = live()) {
      const id = steps[i].id;
      if (AUTO_STEPS.includes(id) && (S.ans[id] == null || i === S.step || S.auto[id])) {
        S.ans[id] = autoValue(id); S.auto[id] = true;
        if (id === "section") { S.ans.sections = [S.ans.section, ...alsoRec(S.ans.section)]; delete S.ans.also; }
        if (id === "facets" || id === "arrange") applyFacets();
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
    if (id === "facets") return (a || []).map(k => facetOf(k)?.label).join("、");
    if (id === "arrange") return a === "split" ? `每个面一个版面（主：${facetOf(mainFacet())?.label || ""}）` : `合成一个版面（${facetOf(mainFacet())?.label || ""}）`;
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
      seriesLookup(name);
    }).catch(() => { if (S.name === name) { S.wd = []; S.wdState = "fail"; if (live()[S.step]?.id === "which") draw(); } });
  }

  // 上级系列：查到的条目里写着「属于哪个系列」的，把系列的名字・说明也查出来（一次请求，查不到就算了）
  async function seriesLookup(name) {
    const ids = [...new Set((S.wd || []).flatMap(x => x.seriesIds || []))].slice(0, 6);
    if (!ids.length) return;
    try {
      const got = await wd({action: "wbgetentities", ids: ids.join("|"), props: "labels|aliases|descriptions", languages: WD_LANGS.join("|")});
      if (S.name !== name) return;
      S.series = ids.map(id => got.entities?.[id]).filter(Boolean).map(ent => {
        const zhHans = label(ent, ["zh-cn", "zh-hans", "zh"]), zhHant = label(ent, ["zh-tw", "zh-hk", "zh-hant"]);
        const ja = label(ent, ["ja"]), en = label(ent, ["en"]);
        return {id: ent.id, title: zhHans || zhHant || ja || en || ent.id, desc: desc(ent) || ent.descriptions?.en?.value || "",
                names: {zhHans, zhHant, ja, ko: label(ent, ["ko"]), en}};
      });
      if (live()[S.step]?.id === "parent") draw();
    } catch (_) {}
  }
  // 这一项所属的系列（选的那个条目的 P179 / P8345 / P361）。已经在关注清单里的 → 推荐挂上去；没有的 → 给「一起加上级」的选项
  const seriesOfPick = () => (S.series || []).filter(x => (wdPick()?.seriesIds || []).includes(x.id));
  const seriesItem = x => tops().find(i => [i.name, ...(i.keywords || [])].some(w => Object.values(x.names).filter(Boolean).some(n => normName(n) === normName(w))));
  const newSeries = () => seriesOfPick().filter(x => !seriesItem(x) && normName(x.title) !== normName(S.name));

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

  // 面：全部列出，有依据的默认勾上（依据写在下面）。勾了几个就放进几个板块
  function askFacets() {
    const plan = facetPlan();
    if (!S.ans.facets) S.ans.facets = defaults("facets");
    const sim = similarItems();
    const toggle = k => { const cur = S.ans.facets; S.ans.facets = cur.includes(k) ? cur.filter(x => x !== k) : [...cur, k];
                          S.auto.facets = false; delete S.ans.focus; delete S.ans.urgent; applyFacets(); draw(); };
    const kwOf = f => uniq([...(f.titles || []), ...(f.kw || []).slice(0, 2).map(w => `${S.name} ${w}`)]).slice(0, 3).join(" / ");
    return h("div", {class: "q"}, h("span", {class: "no"}, no()),
      h("h3", {}, plan.type === "media" ? `「${S.name}」的哪几面要关注？可以多选` : `「${S.name}」关注哪几方面？可以多选`),
      h("p", {}, plan.type === "media"
        ? "按维基数据找到的条目推荐（有依据的已经勾上），其他的也能勾。每个面会自动加一套搜索词，放进对应的板块。"
        : "名字是普通词，只用名字会收进很多不相关的新闻，所以按面来收：每个面的词和名字同时出现才收。推荐的已经勾上。"),
      sim.length ? h("p", {class: "simnote"}, `已经有相近的关注项：${sim.map(i => `「${i.name}」`).join("")}。想往里加，可以在上面的列表里点「改」；也可以在后面「属于哪个」一问挂到它下面。`) : null,
      h("div", {class: "opts facets", role: "group"}, plan.list.map(f => h("button", {type: "button", class: "opt", "aria-pressed": String(S.ans.facets.includes(f.key)),
        onclick: () => toggle(f.key)},
        h("span", {class: "fh"}, f.label, h("i", {class: "fsec"}, secOf(f.sec).ja), f.rec ? h("i", {class: "frec"}, "推荐") : null),
        h("small", {}, f.ev?.length ? `依据：${f.ev.slice(0, 2).map(x => x.title + (x.desc ? `（${x.desc}）` : "")).join("、")}` : (f.hint || "")),
        h("small", {}, `搜索词：${kwOf(f)}`)))),
      nav(S.ans.facets.length > 0));
  }
  // 怎么放：主面（主项「名字」放的板块）＋ 每个面一个版面放在各自的板块（下级，不同的板块都看得到对应的新闻）或合成一个版面（其他板块放乗換駅）
  function askArrange() {
    if (!S.ans.arrange) S.ans.arrange = defaults("arrange");
    const fs = chosenFacets(), main = mainFacet(), rec = defaults("arrange"), mainSec = facetOf(main).sec;
    const set = (k, v) => { S.ans[k] = v; S.auto.arrange = false; applyFacets(); draw(); };
    const groups = Object.entries(facetGroups());
    const nameOf = ([sec, g]) => sec === mainSec ? S.name : `${S.name} ${g[0].tail || g[0].label}`;
    const others = groups.filter(([sec]) => sec !== mainSec).map(([sec]) => secOf(sec).ja);
    const split = h("button", {type: "button", class: "opt", "aria-pressed": String(S.ans.arrange === "split"), onclick: () => set("arrange", "split")},
      "每个板块一个版面" + (rec === "split" ? "（推荐）" : ""),
      h("small", {}, groups.map(([sec, g]) => `「${nameOf([sec, g])}」→ ${secOf(sec).ja}（${g.map(f => f.label).join("・")}）`).join("、")),
      h("small", {}, "每个板块都看得到对应的新闻。同一个板块里只有一个版面：同一板块的面合在一起（漫画・アニメ・映画都在「作品」里 → 一个版面，小分类「シリーズ」）；同一条新闻只出现在一个版面。"));
    const merge = h("button", {type: "button", class: "opt", "aria-pressed": String(S.ans.arrange !== "split"), onclick: () => set("arrange", "merge")},
      "全部合成一个版面" + (rec === "merge" ? "（推荐）" : ""),
      h("small", {}, `新闻都在「${secOf(mainSec).ja}」的一个版面里` + (others.length ? `；${others.join("・")}的目录里放「⇄ 乗換」站，点了跳过去。` : "。")));
    return h("div", {class: "q"}, h("span", {class: "no"}, no()), h("h3", {}, "怎么放？"),
      h("div", {class: "opts", role: "radiogroup"}, split, merge),
      h("div", {class: "subrow"}, h("h4", {}, `「${S.name}」本身放在哪个板块？（主）`),
        h("div", {class: "opts", role: "radiogroup"}, groups.map(([sec, g]) => h("button", {type: "button", class: "opt", "aria-pressed": String(mainSec === sec),
          onclick: () => set("mainFacet", g[0].key)}, `${secOf(sec).ja}（${g.map(f => f.label).join("・")}）`)))),
      nav(true));
  }

  // 板块：可以多选。版面只有一个，放在「主板块」；其他板块的目录里放「乗換」的站，点了跳到同一个版面（同一条新闻只出现一次）。
  // 推荐：它自己本来的板块 ＋ 选了的关注方面带的板块（ちいかわ：ショッピング ＋「动画、电影、活动」→ 作品）
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
      h("p", {}, "比如 ちいかわ 既是周边又有动画，就选「ショッピング」和「作品」。版面只有一个，放在主板块；其他板块的目录里放一个「⇄ 乗換」的站，" +
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
    const pick = v => { S.ans.parent = v; S.auto.parent = false; delete S.ans.subs; S.ans.newParent = null;
                        S.ans.section = v ? (CFG.items.find(i => i.name === v) || {}).section : undefined; };
    const pickNew = x => { const nm = x.names.ja || x.title; S.ans.parent = nm; S.ans.newParent = {...x, name: nm}; S.auto.parent = false;
                           delete S.ans.subs; S.ans.section = undefined; };
    const fresh = newSeries();
    const opts = [...cand.map(i => ({v: i.name, label: i.name, hint: `推荐 · 跟着它放在「${secOf(i.section).ja}」` +
                    (seriesOfPick().some(x => seriesItem(x) === i) ? "（维基数据：属于这个系列）" : "")})),
                  ...fresh.map(x => ({v: "new:" + x.id, x, label: `一起添加上级「${x.names.ja || x.title}」`,
                    hint: `维基数据：「${S.name}」属于这个系列${x.desc ? `（${x.desc}）` : ""}。会先加它，再把「${S.name}」挂在它下面`})),
                  {v: "", label: "不属于任何一个", hint: "单独一个版面"}];
    const cur = S.ans.newParent ? "new:" + S.ans.newParent.id : S.ans.parent;
    const sel = h("select", {"aria-label": "从全部关注项里选上级", onchange: ev => { if (ev.target.value) { pick(ev.target.value); next(); } }},
      h("option", {value: ""}, "其他关注项…"), rest.map(i => h("option", {value: i.name, selected: S.ans.parent === i.name}, `${i.name}（${secOf(i.section).ja}）`)));
    return h("div", {class: "q"}, h("span", {class: "no"}, no()), h("h3", {}, fresh.length ? `「${S.name}」属于哪个系列？` : `「${S.name}」属于哪个已有的关注项？`),
      h("p", {}, "同一个 IP、系列、品牌里的一部作品或一个商品，挂在它下面（比如「ちいかわ アニメ」挂在「ちいかわ」下面）。" +
                 "放在同一个板块，同一条新闻只出现在下级的版面。只做一层。"),
      h("div", {class: "opts", role: "radiogroup"}, opts.map(o => h("button", {type: "button", class: "opt", "aria-pressed": String(cur === o.v),
        onclick: () => { if (o.x) pickNew(o.x); else pick(o.v); next(); }}, o.label, h("small", {}, o.hint)))),
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

  // 一个面的搜索词・匹配规则：作品・IP 型 = 具体作品名（映画ちいかわ）＋「名字 面的词」，匹配用名字（专有名词）；
  // 题材型 = 「名字 面的词」，匹配要名字和面的词同时出现（「猫」单独会收进很多不相关的）
  function facetWords(f, official, alias, topic) {
    const heads = uniq([official[0], wdPick()?.names?.ja].filter(Boolean)).slice(0, 2);
    const kw = uniq([...(f.titles || []), ...heads.flatMap(n => (f.kw || []).slice(0, 2).map(w => `${n} ${w}`))]);
    const match = topic ? [`re:(?is)(?=.*(${alias}))(?=.*(${f.re}))`] : uniq([...official, ...(f.titles || [])]);
    return {kw, match};
  }

  function build() {
    const pick = wdPick(), base = S.original || {}, names = pick?.names || {};
    const k = kindOf(), split = S.ans.arrange === "split" && multiSec();
    const fs = chosenFacets(), topic = facetPlan().type === "topic", main = fs.length ? mainFacet() : null;
    const mainSec = main ? facetOf(main).sec : null;
    // 分开时主项只管主面所在板块的面（和不属于任何面的选项）；其他板块的面给下级
    const focus = chosenFocus().filter(f => !split || !f.facet || facetOf(f.facet)?.sec === mainSec);
    const players = uniq((S.ans.player || "").split(/[,，、\n]+/));
    const official = uniq([S.mode === "edit" ? (base.keywords || [])[0] || S.name : S.name,
                           names.zhHant, names.zhHans, names.ja, names.ko, names.en]);
    const extra = focus.flatMap(f => f.kw || []).map(t => t.replace("{n}", S.name).replace("{en}", names.en || S.name).replace("{ja}", names.ja || S.name));
    const names4re = S.mode === "edit" && !pick ? uniq(base.match || base.keywords || [S.name]) : uniq([...official, ...(pick?.aliases || [])]);
    // 面：主项用的面（分开时只有主面）的搜索词・匹配规则
    const mine = fs.filter(f => !split || f.sec === mainSec).map(f => facetWords(f, official, names4re.slice(0, 10).map(esc).join("|"), topic));
    const keywords = S.mode === "edit" && !pick ? uniq([...(base.keywords || [S.name]), ...extra, ...players])
                                                : uniq([...(topic ? [] : official), ...mine.flatMap(x => x.kw), ...extra, ...players, ...official]).slice(0, 12);
    const match = S.mode === "edit" && !pick ? uniq([...(base.match || base.keywords || [S.name]), ...players])
                : topic && mine.length ? uniq([...mine.flatMap(x => x.match), ...players])
                : uniq([...official, ...(pick?.aliases || []), ...mine.flatMap(x => x.match), ...players]).slice(0, 30);
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
      also: parent || split ? {} : S.ans.also || (S.ans.sections ? Object.fromEntries(S.ans.sections.filter(x => x !== section).map(x => [x, alsoSubs(x)])) : base.also || {}),
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
    if (fs.length) d.notes = (d.notes || "") + `面：${fs.map(f => f.label).join("、")}${split ? `（分开，主：${facetOf(main).label}）` : ""}。`;
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

  // 每个板块一个版面：主项所在以外的板块，各做一个下级（parent = 主项），同一板块的面合在一起（派生の順，名字用最「元」的面）；
  // 那些面的条目（AniList / TMDB / Steam）的编号也带上，主项的板块里放乗換駅（also）。同一件事上下级都收到时只留在下级（render._dedupe_parents）
  function buildChildren(d) {
    if (S.mode !== "add" || S.ans.arrange !== "split" || !multiSec()) return [];
    const main = mainFacet(), mainSec = facetOf(main).sec, topic = facetPlan().type === "topic";
    const official = uniq([S.name, ...((wdPick()?.names && Object.values(wdPick().names)) || [])]).slice(0, 6);
    const alias = uniq([...official, ...(wdPick()?.aliases || [])]).slice(0, 10).map(esc).join("|");
    const urgentIds = (S.ans.urgent || []).includes("none") ? [] : S.ans.urgent || [];
    return Object.entries(facetGroups()).filter(([sec]) => sec !== mainSec).map(([sec, g]) => {
      const head = g[0], keys = g.map(f => f.key), ws = g.map(f => facetWords(f, official, alias, topic));
      const focus = chosenFocus().filter(o => keys.includes(o.facet));
      const titles = uniq(g.flatMap(f => f.titles || []));
      const c = {
        type: KINDS[head.kind]?.type || "product", parent: S.name, section: sec, subs: withSeries(sec, facetSubs(head), g.length),
        also: {[d.section]: {...d.subs}},
        keywords: uniq([...ws.flatMap(w => w.kw), ...official.map(n => `${n} ${head.tail || head.kw?.[0] || ""}`.trim())]).slice(0, 12),
        match: topic ? ws.flatMap(w => w.match) : [`re:(?is)(?=.*(${alias}))(?=.*(${g.map(f => f.re).join("|")}))`, ...titles],
        exclude: d.exclude || [], news_langs: d.news_langs, size: "M",
        priority: focus.map(o => o.priority).filter(Boolean).join("；"),
        urgent_patterns: focus.filter(o => o.urgent && urgentIds.includes(o.id)).map(o => `(${alias}).{0,30}${o.urgent}`),
        notes: `「${S.name}」的${g.map(f => f.label).join("・")}。` + g.flatMap(f => (f.ev || []).slice(0, 1)).filter(x => x.desc)
          .map(x => `维基数据：${x.title}（${x.desc}）。`).join(""),
      };
      for (const f of g) {
        const hit = (f.ev || [])[0] || {};
        if (hit.anilist && f.key === "anime" && !c.anilist_id) c.anilist_id = Number(hit.anilist);
        if (hit.anilistManga && f.key === "manga" && !c.anilist_id) { c.anilist_id = Number(hit.anilistManga); c.anilist_type = "MANGA"; }
        if (hit.tmdb && ["anime", "drama", "movie"].includes(f.key) && !c.tmdb) c.tmdb = hit.tmdb;
        if (hit.steam && f.key === "game" && !c.steam_appid) c.steam_appid = Number(hit.steam);
      }
      return {name: `${S.name} ${head.tail || head.label}`, on: true, config: c, label: g.map(f => f.label).join("・")};
    });
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
    const np = S.ans.newParent && d.parent === S.ans.newParent.name ? S.ans.newParent : null;
    const parentSel = h("select", {"data-k": "parent"}, h("option", {value: ""}, "不属于（单独一个版面）"),
      np ? h("option", {value: np.name, selected: true}, `${np.name}（新加的上级系列，和这一项放在同一个板块）`) : null,
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
    // 每个面一个版面：一起加的下级（名字可以改，不要的取消勾）
    if (!S.kids || S.kidsFor !== JSON.stringify([S.ans.facets, S.ans.arrange, S.ans.mainFacet])) {
      S.kids = buildChildren(d); S.kidsFor = JSON.stringify([S.ans.facets, S.ans.arrange, S.ans.mainFacet]);
    }
    const kids = S.kids.length ? h("div", {class: "kids"}, h("span", {}, `一起加的版面（挂在「${S.name}」下面，放在各自的板块）`),
      S.kids.map((x, i) => h("label", {class: "kid"}, h("input", {type: "checkbox", checked: x.on, onchange: ev => { x.on = ev.target.checked; }}),
        h("input", {type: "text", value: x.name, maxlength: 80, "aria-label": `${x.label}的版面名`, oninput: ev => { x.name = ev.target.value.trim(); }}),
        h("small", {}, `${x.label} → ${secOf(x.config.section).ja}・${Object.values(x.config.subs).join(" · ")} · 搜索词：${x.config.keywords.slice(0, 3).join(" / ")}`)))) : null;
    const form = h("div", {class: "rv"},
      S.mode === "add" ? h("label", {}, h("span", {}, "名字"), h("small", {}, "简报上显示的名字"),
        h("input", {type: "text", value: S.name, maxlength: 80, "data-k": "name"})) : null,
      kids,
      h("div", {class: "two"}, h("label", {}, h("span", {}, "类型"), types),
        h("label", {}, h("span", {}, "板块"), section)),
      d.parent || S.kids.length ? null : alsoBox,
      (tops().length || np) && !S.kids.length ? h("label", {}, h("span", {}, "上级"), h("small", {}, "同一个 IP・系列・品牌里的作品或商品，挂在它下面；板块跟着上级"), parentSel) : null,
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
    // 一起添加的上级系列（维基数据的 P179 / P8345 / P361）：先加系列，处理时它已经在了，这一项才能挂上去
    const np = S.mode === "add" && S.ans.newParent && d.parent === S.ans.newParent.name && !CFG.items.some(i => i.name === d.parent) ? S.ans.newParent : null;
    if (np) {
      const names = uniq([np.name, ...Object.values(np.names || {})]);
      const first = (secOf(d.section).schemes || [])[0];
      const series = first && (first.values || []).map(vOf).includes("シリーズ") ? {[first.id]: "シリーズ"} : {};
      try {
        const rp = await fetch(`${CFG.url}/rest/v1/rpc/submit_item`, {method: "POST", headers: {apikey: CFG.key, "Content-Type": "application/json"},
          body: JSON.stringify({p_action: "add", p_name: np.name, p_config: {type: d.type, section: d.section, subs: {...d.subs, ...series},
            keywords: names.slice(0, 8), match: names, news_langs: d.news_langs, size: "M",
            notes: `维基数据：${np.title}${np.desc ? `（${np.desc}）` : ""}。设置页加「${name}」时一起加的上级系列。`}})});
        if (!rp.ok) { const err = await rp.json().catch(() => ({})); sayMsg("上级系列没存上：" + (err.message || rp.status), "err"); btn.disabled = false; return; }
      } catch (_) { sayMsg("连不上数据库", "err"); btn.disabled = false; return; }
    }
    try {
      const r = await fetch(`${CFG.url}/rest/v1/rpc/submit_item`, {method: "POST",
        headers: {apikey: CFG.key, "Content-Type": "application/json"},
        body: JSON.stringify({p_action: S.mode, p_name: name, p_config: config})});
      if (r.ok) {
        // 下级（每个面一个版面）：主项之后按顺序提交（处理时上级已经在了）
        const kids = (S.kids || []).filter(x => x.on && x.name && !CFG.items.some(i => i.name === x.name));
        const done = [];
        for (const x of kids) {
          const rr = await fetch(`${CFG.url}/rest/v1/rpc/submit_item`, {method: "POST", headers: {apikey: CFG.key, "Content-Type": "application/json"},
            body: JSON.stringify({p_action: "add", p_name: x.name, p_config: {...x.config, parent: name}})}).catch(() => null);
          if (rr?.ok) done.push(x.name);
        }
        const what = S.mode === "edit" ? `已提交「${name}」的修改 ✓ 进度看下面「最近提交的」，会自动刷新`
                                       : `已提交${np ? `上级「${np.name}」和` : ""}「${name}」${done.length ? `和 ${done.map(n => `「${n}」`).join("")}` : ""} ✓ 进度看下面「最近提交的」，会自动刷新`;
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
  function reset() { S = fresh(); S.kids = null; draw(); }

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
