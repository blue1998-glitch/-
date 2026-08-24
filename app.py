import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone, timedelta
import json
import os
import requests

st.set_page_config(page_title="台股動能 RS 排行與風控儀表板", layout="wide", initial_sidebar_state="collapsed")

DATA_FILE, TW_TZ = "portfolio.json", timezone(timedelta(hours=8))

def get_tw_now_str(): return datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")

if "last_portfolio_refresh" not in st.session_state:
    st.session_state.last_portfolio_refresh = get_tw_now_str()

# ==========================================
# 官方標準券商下單簡稱對照庫 (高壓濃縮版)
# ==========================================
_RAW_NAMES = "1101:台泥,1102:亞泥,1103:嘉泥,1104:環泥,1109:信大,1110:東泥,1201:味全,1210:大成,1216:統一,1217:愛之味,1227:佳格,1229:聯華,1231:聯華食,1232:大統益,1233:天仁,1234:黑松,1236:宏亞,1240:茂生農經,1259:安心,1268:漢來美食,1301:台塑,1303:南亞,1304:台聚,1305:華夏,1307:三芳,1308:亞聚,1310:台苯,1312:國喬,1313:聯成,1314:中石化,1315:達新,1316:上曜,1321:大洋,1323:永裕,1326:台化,1336:台翰,1337:再生-KY,1339:昭輝,1340:勝悅-KY,1341:富林-KY,1342:八貫,1402:遠東新,1409:新纖,1414:東和,1416:廣豐,1417:嘉裕,1419:新紡,1432:大魯閣,1434:福懋,1435:中福,1436:華友聯,1437:勤益控,1438:三地開發,1439:雋揚,1440:南紡,1442:名軒,1443:立益物流,1444:力麗,1445:大宇,1447:力鵬,1449:佳和,1451:年興,1452:宏益,1453:大將,1454:台富,1455:集盛,1456:怡華,1457:宜進,1459:聯發,1460:宏遠,1463:強盛,1464:得力,1465:偉全,1466:聚隆,1467:南緯,1468:昶和,1470:大統新創,1471:首利,1472:三洋實業,1473:台南,1474:弘裕,1475:業旺,1503:士電,1504:東元,1506:正道,1513:中興電,1515:力山,1517:利奇,1519:華城,1524:耿鼎,1525:江申,1526:日馳,1527:鑽全,1528:恩德,1531:高林,1532:勤美,1535:中宇,1537:廣隆,1540:喬福,1558:伸興,1563:巧新,1565:精華,1569:濱川,1582:信錦,1589:永冠-KY,1590:亞德客-KY,1593:祺驊,1595:川寶,1598:岱宇,1603:華電,1604:聲寶,1605:華新,1608:華榮,1609:大亞,1611:中電,1612:宏泰,1614:三洋電,1615:大山,1616:億泰,1617:榮星,1618:合機,1626:艾美特-KY,1702:南僑,1708:東鹼,1709:和益,1710:東聯,1711:永光,1712:興農,1714:和桐,1717:長興,1718:中纖,1720:生達,1722:台肥,1723:中碳,1725:元禎,1726:永記,1727:中華化,1730:花仙子,1731:美吾華,1732:毛寶,1733:五鼎,1734:杏輝,1736:喬山,1737:臺鹽,1742:台蠟,1752:南光,1760:寶齡富錦,1762:中化生,1776:展宇,1777:生泰,1783:和康生,1784:訊聯,1786:科妍,1788:杏昌,1789:神隆,1795:美時,1802:台玻,1805:寶徠,1806:冠軍,1808:潤隆,1809:中釉,1810:和成,1815:富喬,1817:凱撒衛,1903:士紙,1904:正隆,1905:華紙,1906:寶隆,1907:永豐餘,1909:榮成,2002:中鋼,2006:東和鋼鐵,2007:燁興,2008:高興昌,2009:第一銅,2010:春源,2012:春雨,2013:中鋼構,2014:中鴻,2015:豐興,2017:官田鋼,2020:美亞,2022:聚亨,2023:燁輝,2024:志聯,2025:千興,2027:大成鋼,2028:威致,2029:盛餘,2030:彰源,2031:新光鋼,2032:新鋼,2033:佳大,2034:允強,2035:唐榮,2038:海光,2059:川湖,2061:風青,2062:橋椿,2063:世鎧,2064:晉椿,2065:世豐,2069:運錩,2070:精湛,2072:世紀風電,2101:南港,2102:泰豐,2103:台橡,2104:國際中橡,2105:正新,2106:建大,2107:厚生,2108:南帝,2109:華豐,2114:鑫永銓,2115:六暉-KY,2201:裕隆,2204:中華,2206:三陽工業,2207:和泰車,2208:台船,2211:長榮鋼,2221:大甲,2239:英利-KY,2241:艾姆勒,2243:宏旭-KY,2247:汎德永業,2248:華勝-KY,2258:鴻華先進-創,2301:光寶科,2302:麗正,2303:聯電,2305:全友,2313:華通,2316:楠梓電,2317:鴻海,2321:東訊,2323:中環,2324:仁寶,2330:台積電,2331:精英,2340:台亞,2342:茂矽,2344:華邦電,2347:聯強,2348:海悅,2351:順德,2352:佳世達,2353:宏碁,2354:鴻準,2356:英業達,2357:華碩,2362:藍天,2364:倫飛,2368:金像電,2371:大同,2373:震旦行,2375:凱美,2377:微星,2379:瑞昱,2380:虹光,2382:廣達,2383:台光電,2390:云辰,2392:正崴,2393:億光,2395:研華,2397:友通,2399:映泰,2408:南亞科,2409:友達,2412:中華電,2413:環科,2414:精技,2415:錩新,2417:圓剛,2421:建準,2424:隴華,2426:鼎元,2427:三商電,2428:興勤,2430:燦坤,2431:聯昌,2432:倚天酷碁-創,2433:互盛電,2434:統懋,2436:偉詮電,2438:翔耀,2439:美律,2440:太空梭,2442:新美齊,2450:神腦,2451:創見,2453:凌群,2454:聯發科,2455:全新,2459:敦吉,2461:光群雷,2462:良得電,2464:盟立,2465:麗臺,2466:冠西電,2468:華經,2471:資通,2474:可成,2476:鉅祥,2478:大毅,2480:敦陽科,2481:強茂,2482:連宇,2483:百容,2484:希華,2485:兆赫,2486:一詮,2489:瑞軒,2491:吉祥全,2493:揚博,2501:國建,2504:國產,2505:國揚,2506:太設,2509:全坤建,2511:太子,2515:中工,2516:新建,2520:冠德,2524:京城,2527:宏璟,2528:皇普,2530:華建,2534:宏盛,2535:達欣工,2536:宏普,2537:聯上發,2538:基泰,2539:櫻花建,2540:愛山林,2542:興富發,2543:皇昌,2545:皇翔,2546:根基,2547:日勝生,2548:華固,2596:綠意,2597:潤弘,2601:益航,2603:長榮,2605:新興,2606:裕民,2607:榮運,2608:大榮,2609:陽明,2610:華航,2611:志信,2612:中航,2613:中櫃,2614:東森,2615:萬海,2616:山隆,2617:台航,2618:長榮航,2630:亞航,2633:高鐵,2634:漢翔,2636:台驊控股,2637:慧洋-KY,2640:大車隊,2641:正德,2642:宅配通,2643:捷迅,2645:長榮航太,2646:星宇航空,2701:萬華,2702:華園,2704:國賓,2705:六福,2706:第一店,2707:晶華,2712:遠雄來,2718:全心,2722:夏都,2723:美食-KY,2727:王品,2729:瓦城,2731:雄獅,2732:六角,2734:易飛網,2736:富野,2739:寒舍,2743:山富,2748:雲品,2751:王座,2752:豆府,2753:八方雲集,2754:亞洲藏壽司,2755:揚秦,2756:聯發國際,2762:世界健身-KY,2801:彰銀,2812:台中銀,2816:旺旺保,2820:華票,2832:台產,2834:臺企銀,2836:高雄銀,2838:聯邦銀,2845:遠東銀,2849:安泰銀,2850:新產,2851:中再保,2852:第一保,2855:統一證,2867:三商壽,2880:華南金,2881:富邦金,2882:國泰金,2883:凱基金,2884:玉山金,2885:元大金,2886:兆豐金,2887:台新金,2889:國票金,2890:永豐金,2891:中信金,2892:第一金,2897:王道銀行,2901:欣欣,2903:遠百,2904:匯僑,2905:三商,2906:高林,2908:特力,2910:統領,2912:統一超,2913:農林,2915:潤泰全,2916:滿心,2937:集雅社,2941:米斯特,2945:三商家購,2948:寶陞,2949:欣新網,3002:歐格,3003:健和興,3005:神基,3006:晶豪科,3008:大立光,3010:華立,3015:全漢,3016:嘉晶,3017:奇鋐,3018:隆銘綠能,3022:威強電,3023:信邦,3024:憶聲,3026:禾伸堂,3027:盛達,3028:增你強,3029:零壹,3031:佰鴻,3033:威健,3034:聯詠,3037:欣興,3040:遠見,3042:晶技,3043:科風,3044:健鼎,3045:台灣大,3046:建碁,3048:益登,3049:精金,3050:鈺德,3051:力特,3052:夆典,3054:立萬利,3055:蔚華科,3056:富華創新,3057:喬鼎,3058:立德,3059:華晶科,3060:銘異,3064:泰偉,3066:李洲,3073:天方能源,3078:僑威,3081:聯亞,3086:華義,3090:日電貿,3092:鴻碩,3093:港建*,3094:聯傑,3114:好德,3115:富榮綱,3118:進階,3128:昇銳,3130:一零四,3135:凌航,3141:晶宏,3147:大綜,3149:正達,3152:璟德,3158:嘉實,3163:波若威,3164:景岳,3167:大量,3176:基亞,3188:鑫龍騰,3189:景碩,3191:雲嘉南,3205:佰研,3213:茂訊,3218:大學光,3219:倚強科,3226:龍鋒,3229:晟鈦,3230:錦明,3231:緯創,3234:光環,3236:千如,3252:海灣,3260:威剛,3265:台星科,3266:昇陽,3284:太普高,3285:微端,3287:廣寰科,3288:點晶,3293:鈊象,3296:勝德,3303:岱稜,3306:鼎天,3308:聯德,3310:佳穎,3312:弘憶股,3321:同泰,3324:雙鴻,3338:泰碩,3339:泰谷,3346:麗清,3349:寶德,3356:奇偶,3357:臺慶科,3360:尚立,3362:先進光,3374:精材,3376:新日興,3388:崇越電,3406:玉晶光,3416:融程電,3434:哲固,3438:類比科,3441:聯一光,3443:創意,3444:利機,3447:展達,3450:聯鈞,3455:由田,3465:進泰電子,3481:群創,3484:崧騰,3485:敘豐,3489:森寶,3490:單井,3491:昇達科,3498:陽程,3501:維熹,3504:揚明光,3508:位速,3511:矽瑪,3512:皇龍,3515:華擎,3516:亞帝歐,3520:華盈,3523:迎輝,3528:安馳,3532:台勝科,3537:堡達,3540:曜越,3541:西柏,3543:州巧,3545:敦泰,3550:聯穎,3555:博士旺,3556:禾瑞亞,3557:嘉威,3570:大塚,3588:通嘉,3591:艾笛森,3597:映興,3605:宏致,3607:谷崧,3611:鼎翰,3615:安可,3617:碩天,3622:洋華,3623:富晶通,3624:光頡,3628:盈正,3629:地心引力,3630:新鉅科,3631:晟楠,3646:艾恩特,3652:精聯,3653:健策,3661:世芯-KY,3673:TPK-KY,3675:德微,3679:新至陞,3680:家登,3684:榮昌,3685:元創精密,3693:營邦,3702:大聯大,3703:欣陸,3705:永信,3706:神達,3707:漢磊,3708:上緯投控,3712:永崴投控,3713:新晶投控,3714:富采,3716:中化控股,3717:聯嘉投控,4102:永日,4104:佳醫,4105:東洋,4106:雃博,4107:邦特,4109:加捷生醫,4111:濟生,4113:聯上,4114:健喬,4116:明基醫,4119:旭富,4120:友華,4121:優盛,4126:太醫,4127:天良,4128:中天,4129:聯合,4131:浩泰,4133:亞諾法,4138:曜亞,4139:馬光-KY,4142:國光生,4147:中裕,4148:全宇生技-KY,4153:鈺緯,4157:太景*-KY,4160:訊聯基因,4161:聿新科,4162:智擎,4163:鐿鈦,4164:承業醫,4167:松瑞藥,4168:醣聯,4169:泰宗,4173:久裕,4174:浩鼎,4175:杏一,4188:安克,4190:佐登-KY,4192:杏國,4198:欣大健康,4205:中華食,4207:環泰,4303:信立,4304:勝昱,4305:世坤,4306:炎洲,4401:東隆興,4402:郡都開發,4406:新昕纖,4413:飛寶企業,4414:如興,4416:三圓,4417:金洲,4419:皇家美食,4420:光明,4430:耀億,4438:廣越,4440:宜新實業,4441:振大環球,4442:竣邦國際-KY,4502:健信,4506:崇友,4510:高鋒,4527:方土霖,4530:天意,4532:瑞智,4535:至興,4536:拓凱,4538:大詠城,4540:全球傳動,4541:晟田,4542:科嶠,4543:萬在,4550:長佳,4551:智伸科,4554:橙的,4556:旭然,4557:永新-KY,4558:寶緯,4560:強信-KY,4561:健椿,4564:元翎,4568:科際精密,4569:六方科-KY,4577:達航科技,4580:捷流閥業,4581:光隆精密-KY,4584:君帆,4588:玖鼎電力,4590:富田,4702:中美實,4706:大恭,4707:磐亞,4711:永純,4716:大立,4720:德淵,4726:永昕,4728:雙美,4735:豪展,4736:泰博,4737:華廣,4739:康普,4743:合一,4746:台耀,4747:強生,4754:國碳科,4760:勤凱,4763:材料-KY,4766:南寶,4767:誠泰科技,4768:晶呈科技,4771:望隼,4772:台特化,4804:大略-KY,4904:遠傳,4905:台聯電,4906:正文,4907:富宇,4923:力士,4924:欣厚-KY,4927:泰鼎-KY,4931:新盛力,4938:和碩,4939:亞電,4943:康控-KY,4946:辣椒,4952:凌通,4953:緯致,4956:光鋐,4961:天鈺,4966:譜瑞-KY,4967:十銓,4971:IET-KY,4972:湯石照明,4973:廣穎,4976:佳凌,4977:眾達-KY,4979:華星光,4995:晶達,5007:三星,5009:榮剛,5011:久陽,5013:強新,5016:松和,5201:凱衛,5202:力新,5206:坤悅,5209:新鼎,5210:寶碩,5211:蒙恬,5212:凌網,5213:亞昕,5215:科嘉-KY,5230:雷笛克光學,5244:弘凱,5269:祥碩,5276:達輝-KY,5278:尚凡,5283:禾聯碩,5284:jpp-KY,5285:界霖,5287:數字,5288:豐祥-KY,5289:宜鼎,5291:邑昇,5292:華懋,5299:杰力,5302:太欣,5306:桂盟,5309:系統電,5310:天剛,5312:寶島極,5314:世紀,5315:光聯,5321:美而快,5324:士開,5328:華容,5340:建榮,5345:馥鴻,5348:正能量智能,5351:鈺創,5353:台林,5356:協益,5364:力麗店,5371:中光電,5381:合騏,5386:青雲,5392:能率,5403:中菲,5410:國眾,5425:台半,5426:振發,5432:新門,5434:崇越,5450:寶緯,5452:佶優,5455:昇益,5457:宣德,5460:同協,5465:富驊,5468:凱鈺,5471:松翰,5474:聰泰,5475:德宏,5478:智冠,5481:華韡,5483:中美晶,5484:慧友,5487:通泰,5488:松普,5489:彩富,5498:凱崴,5508:永信建,5511:德昌,5512:力麒,5514:三豐,5515:建國,5516:雙喜,5519:隆大,5520:力泰,5521:工信,5522:遠雄,5523:豐謙,5525:順天,5529:鉅陞,5530:龍巖,5533:皇鼎,5534:長虹,5538:東明-KY,5547:久舜,5548:安倉,5603:陸海,5604:中連,5607:遠雄港,5608:四維航,5609:中菲行,5701:劍湖山,5703:亞都,5704:知本老爺,5706:鳳凰,5864:致和證,5871:中租-KY,5876:上海商銀,5880:合庫金,5902:德記,5903:全家,5904:寶雅,5906:台南-KY,5907:大洋-KY,6021:美好證,6024:群益期,6026:福邦證,6028:公勝保經,6101:寬魚國際,6104:創惟,6108:競國,6112:邁達特,6116:彩晶,6120:達運,6121:新普,6122:擎邦,6123:上奇,6124:業強,6125:廣運,6126:信音,6128:上福,6130:上亞科技,6133:金橋,6134:萬旭,6136:富爾特,6139:亞翔,6140:訊達,6141:柏承,6144:得利影,6148:驊宏資,6150:撼訊,6152:百一,6153:嘉聯益,6154:順發,6155:鈞寶,6156:松上,6160:欣技,6164:華興,6165:浪凡,6167:久正,6168:宏齊,6170:統振,6171:大城地產,6173:信昌電,6174:安碁,6177:達麗,6179:亞通,6180:橘子,6182:合晶,6183:關貿,6187:萬潤,6189:豐藝,6192:巨路,6195:詩肯,6197:佳必琪,6202:盛群,6204:艾華,6206:飛捷,6207:雷科,6209:今國光,6212:理銘,6213:聯茂,6214:精誠,6216:居易,6218:豪勉,6219:富旺,6221:晉泰,6222:上揚,6223:旺矽,6224:聚鼎,6225:天瀚,6226:光鼎,6240:松崗,6241:易通展,6248:沛波,6259:百徽,6263:普萊德,6264:富裔,6265:方土昶,6266:泰詠,6269:台郡,6270:倍微,6271:同欣電,6274:台燿,6275:元山,6277:宏正,6278:台表科,6279:胡連,6281:全國電,6290:良維,6292:迅德,6294:智基,6409:旭隼,6416:瑞祺電通,6418:詠昇,6419:京晨科,6423:億而得,6426:統新,6431:光麗-KY,6435:大中,6442:光聖,6446:藥華藥,6461:益得,6464:台數科,6465:威潤,6469:大樹,6472:保瑞,6474:華豫寧,6477:安集,6482:弘煜科,6488:環球晶,6491:晶碩,6494:九齊,6496:科懋,6505:台塑化,6506:雙邦,6508:惠光,6509:聚和,6512:啟發電,6515:穎崴,6516:勤崴國際,6517:保勝光學,6525:捷敏-KY,6527:明達醫,6530:創威,6531:愛普*,6532:瑞耘,6533:晶心科,6534:正瀚-創,6538:倉和,6541:泰福-KY,6542:隆中,6547:高端疫苗,6548:長科*,6550:北極星藥業-KY,6569:醫揚,6570:維田,6573:虹揚-KY,6574:霈方,6576:逸達,6578:達邦蛋白,6581:鋼聯,6582:申豐,6584:南俊國際,6585:鼎基,6588:東典光電,6589:台康生技,6590:普鴻,6592:和潤企業,6593:台灣銘板,6596:寬宏藝術,6597:立誠,6605:帝寶,6609:瀧澤科,6612:奈米醫材,6615:慧智,6617:共信-KY,6620:漢達,6624:萬年清,6625:必應,6629:泰金-KY,6637:醫影,6641:基士德-KY,6645:金萬林-創,6651:全宇昕,6654:天正國際,6658:聯策,6661:威健生技,6662:樂斯科,6666:羅麗芬-KY,6668:中揚光,6669:緯穎,6670:復盛應用,6671:三能-KY,6672:騰輝電子-KY,6674:鋐寶科技,6684:安格,6689:伊雲谷,6690:安碁資訊,6691:洋基工程,6692:進金生,6693:廣閎科,6697:東捷資訊,6703:軒郁,6712:長聖,6715:嘉基,6716:應廣,6721:信實,6727:亞泰金屬,6728:上洋,6730:常廣,6733:博晟生醫,6741:91APP*-KY,6742:澤米,6751:智聯服務,6752:叡揚,6753:龍德造船,6754:匯僑設計,6756:威鋒電子,6757:台灣虎航-創,6761:穩得,6762:達亞,6763:綠界科技*,6768:志強-KY,6770:力積電,6771:平和環保-創,6776:展碁國際,6781:AES-KY,6782:視陽,6788:華景電,6790:永豐實,6792:詠業,6794:向榮生技-創,6796:晉弘,6803:崑鼎,6804:明係,6805:富世達,6807:峰源-KY,6811:宏碁資訊,6829:千附精密,6830:汎銓,6834:天二科技,6840:東研信超,6841:長佳智能,6855:數泓科,6859:伯特光,6865:偉康科技,6870:騰雲,6874:倍力,6881:潤德,6884:海柏特,6885:全福生技,6887:寶綠特-KY,6890:來億-KY,6895:宏碩系統,6901:鑽石生技,6904:伯鑫,6907:雅特力-KY,6909:創控,6913:鴻呈,6914:阜爾運通,6916:華凌,6918:愛派司,6919:康霈*,6921:嘉雨思,6922:宸曜,6923:中台,6924:榮惠-KY,6925:意藍,6928:攸泰科技,6929:佑全,6931:青松健康,6933:AMAX-KY,6936:永鴻生技,6945:圓祥生技,6949:沛爾生醫-創,6951:青新-創,6952:大武山,6953:家碩,6957:裕慶-KY,6958:日盛台駿,6962:ITH-KY,6965:中傑-KY,6967:汎瑋材料,6968:萬達寵物,6969:成信實業-創,6996:力領科技,6997:博弘,7402:邑錡,7547:碩網資訊,7556:意德士,7584:樂意,7610:聯友金屬-創,7631:聚賢研發-創,7642:昶瑞機電,7703:銳澤,7704:明遠精密,7705:三商餐飲,7708:全家餐飲,7709:榮田,7711:永擎,7712:博盛半導體,7713:威力德,7714:創泓科技,7715:裕山,7718:友鋮,7722:LINEPAY,7723:築間,7732:金興精密,7738:東聯互動,7743:金利食安,7744:崴寶,7749:意騰-KY,7751:竑騰,7753:星亞,7760:享溫馨,7767:仁大資訊,7768:頌勝,7780:大研生醫,7782:光速火箭,7786:東方風能,7788:松川精密,7792:安葆,7795:長廣,7799:禾榮科,7805:威聯通,7810:捷創科技,7811:民盛應用,7820:立盈科技,7822:倍利,7827:漢康生技,7828:創新服務,7842:天能綠電,8011:台通,8016:矽創,8021:尖點,8033:雷虎,8039:台虹,8043:蜜望實,8046:南電,8047:星雲,8049:晶采,8070:長華*,8071:能率網通,8076:伍豐,8077:洛碁,8081:致新,8083:瑞穎,8084:巨虹,8085:福華,8087:麗升,8089:康全電訊,8093:保銳,8099:大綜,8101:華冠,8102:傑霖科技,8103:瀚荃,8107:大億金茂,8109:博大,8110:華東,8111:立碁,8112:至上,8155:博智,8162:微矽電子-創,8163:達方,8176:智捷,8201:無敵,8213:志超,8222:寶一,8234:新漢,8261:富鼎,8271:宇瞻,8277:商丞,8284:三竹,8299:群聯,8341:日友,8349:恒耀,8354:冠好,8358:金居,8367:建新國際,8390:金益鼎,8401:白紗科,8403:盛弘,8404:百和興業-KY,8410:森田,8415:大國鋼,8421:旭源,8422:可寧衛,8423:保綠-KY,8424:惠普,8426:紅木-KY,8429:金麗-KY,8432:東生華,8433:弘帆,8435:鉅邁,8436:大江,8438:昶昕,8440:綠電,8442:威宏-KY,8443:阿瘦,8444:綠河-KY,8446:華研,8454:富邦媒,8455:大拓-KY,8462:柏文,8463:潤泰材,8464:億豐,8472:納維康,8473:山林水,8476:台境,8481:政伸,8482:商億-KY,8487:愛爾達-創,8488:吉源-KY,8489:三貝德,8905:裕國,8906:花王,8908:欣雄,8916:光隆,8917:欣泰,8923:時報,8926:台汽電,8927:北基,8928:鉅明,8930:青鋼,8931:大汽電,8932:智通,8935:邦泰,8936:國統,8937:合騏,8941:關中,8942:森鉅,8996:高力,9103:美德醫療-DR,9105:泰金寶-DR,9110:越南控-DR,9136:巨騰-DR,9802:鈺齊-KY,9902:台火,9904:寶成,9905:大華,9906:欣巴巴,9907:統一實,9908:大台北,9910:豐泰,9911:櫻花,9912:偉聯,9914:美利達,9917:中保科,9918:欣天然,9919:康那香,9921:巨大,9924:福興,9925:新保,9926:新海,9927:泰銘,9928:中視,9929:秋雨,9930:中聯資,9931:欣高,9933:中鼎,9934:成霖,9935:慶豐富,9937:全國,9938:百和,9939:宏全,9940:信義,9941:裕融,9942:茂順,9943:好樂迪,9944:新麗,9945:潤泰新,9946:三發地產,9949:琉園,9950:萬國通,9951:皇田,9955:佳龍,9960:邁達康,9962:有益"
OFFICIAL_STOCK_NAMES = dict(item.split(":") for item in _RAW_NAMES.split(","))

def clean_stock_name(name, symbol=None):
    if symbol and (sym_str := str(symbol).strip().upper()) in OFFICIAL_STOCK_NAMES:
        return OFFICIAL_STOCK_NAMES[sym_str]
    raw = str(name).strip() if name else (str(symbol) if symbol else "")
    for suffix in ["股份有限公司台灣分公司", "股份有限公司", "有限股份公司", "有限公司", "(股)公司", "（股）公司"]:
        raw = raw.replace(suffix, "")
    return raw.strip()

# ==========================================
# 順勢大師操作法則：動能狀態分類引擎
# ==========================================
def get_trend_master_status(row):
    rs, badge, r_5d = row.get("rs_rating", 50), str(row.get("pattern_badge", "")), row.get("r_5d", 0.0)
    if rs >= 95: return "👑 頂級領袖・突破新高" if "新高" in badge or r_5d >= 10.0 else ("🎯 頂級VCP・即將噴出" if "VCP" in badge else "🚀 極致飆股・主升奔馳")
    if rs >= 90: return "🎯 VCP蓄勢・突破在即" if "VCP" in badge else ("⭐ 領袖新高・順風追擊" if "新高" in badge else "🚀 狂暴主升・沿線抱牢")
    if rs >= 80: return "🎯 VCP收縮・縮量待發" if "VCP" in badge else ("⭐ 區間突破・趨勢確立" if "新高" in badge else ("⚠️ 短線強彈・觀察季線" if "反彈" in badge else "⚡ 強大多頭・順勢推升"))
    if rs >= 75: return "⚠️ 左側反彈・上方有壓" if "反彈" in badge else ("🎯 底部收斂・轉強蓄勢" if "VCP" in badge else "🔥 突破初升・動能成型")
    return "📦 區間整理・等待表態" if rs >= 50 else "⛔ 弱勢落後・左側不碰"

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for d in data: d["name"] = clean_stock_name(d.get("name"), d.get("symbol"))
            return data
    except Exception: return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

@st.cache_data(ttl=60)
def load_market_data():
    if os.path.exists("market_rankings.json"):
        try:
            data = json.load(open("market_rankings.json", "r", encoding="utf-8"))
            if data: return data, f"本機檔案載入成功 (產出時間: {datetime.fromtimestamp(os.path.getmtime('market_rankings.json'), tz=TW_TZ).strftime('%Y-%m-%d %H:%M:%S')})"
        except: pass
    try:
        res = requests.get("https://raw.githubusercontent.com/blue1998-glitch/-/main/market_rankings.json", timeout=8)
        if res.status_code == 200 and (data := res.json()):
            for item in data: item["name"] = clean_stock_name(item.get("name"), item.get("symbol"))
            return data, f"GitHub 線上同步成功 (同步時間: {get_tw_now_str()})"
    except Exception as e: return [], f"連線異常: {str(e)}"
    return [], "無可用資料"

def get_stock_rs_info(symbol, market_list):
    sym_clean = str(symbol).strip().upper()
    return next((item for item in market_list if str(item.get("symbol", "")).strip().upper() == sym_clean), None)

# 優化：單次 API 抓取取代原本的兩次
def fetch_stock_and_momentum(symbol, market, entry_date_str):
    ticker = f"{symbol}.TWO" if market in ["上櫃", "TWO (上櫃)"] else f"{symbol}.TW"
    try:
        df_all = yf.Ticker(ticker).history(period="6mo")
        if df_all.empty: return None, None, None, 0.0, 0.0, 0.0
        
        c_p = round(float(df_all["Close"].iloc[-1]), 2)
        ma20 = round(float(df_all["Close"].tail(20).mean()), 2)
        
        df_entry = df_all.loc[entry_date_str:]
        if df_entry.empty: df_entry = df_all.tail(20)
        m_h = round(float(df_entry["High"].max()), 2)
        
        cls = df_all["Close"]
        def ret(d): return round(((cls.iloc[-1] - cls.iloc[-d])/cls.iloc[-d])*100, 2) if len(cls)>=d else 0.0
        r_5d = ret(6)
        r_1m = ret(21) or r_5d
        r_1q = ret(61) or r_1m
        return c_p, m_h, ma20, r_5d, r_1m, r_1q
    except: return None, None, None, 0.0, 0.0, 0.0

def calc_pnl(shares, avg_cost, current_price, fee_discount):
    fees = 0.001425 * fee_discount
    total_buy = (shares * avg_cost) * (1 + fees)
    total_sell = (shares * current_price) * (1 - fees - 0.003)
    net_pnl = round(total_sell - total_buy)
    roi = round((net_pnl / total_buy) * 100, 2) if total_buy > 0 else 0.0
    brk = round(avg_cost * (1 + fees * 2 + 0.003), 2)
    return net_pnl, roi, brk

market_rankings, db_status = load_market_data()
st.title("🚀 台股動能 RS 領袖排行與風控儀表板")

with st.expander("🛡️ 系統五大自動化量化風控機制速查指南（交易紀律鐵律）", expanded=True):
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    fc1.markdown("**1. 🔴 初始固定停損**\n\n<span style='font-size:14px;color:gray'>跌破設定趴數（預設 -7%）無條件停損，截斷重大虧損。</span>", unsafe_allow_html=True)
    fc2.markdown("**2. 🛡️ 動態保本停損**\n\n<span style='font-size:14px;color:gray'>波段獲利達標（預設 +8%）自動啟動，停損點推至零虧損保本價。</span>", unsafe_allow_html=True)
    fc3.markdown("**3. 🟣 高點回檔停利**\n\n<span style='font-size:14px;color:gray'>自歷史最高價回檔達設定幅度（預設 10%），觸發分批減碼。</span>", unsafe_allow_html=True)
    fc4.markdown("**4. 🟠 月線乖離過熱**\n\n<span style='font-size:14px;color:gray'>現價與 20MA 正乖離過大（預設 +30%），短線過熱建議調節。</span>", unsafe_allow_html=True)
    fc5.markdown("**5. ⏳ 時間動能停損**\n\n<span style='font-size:14px;color:gray'>持有天數達標（預設 10 天）且損益在 ±2% 內停滯，建議換股。</span>", unsafe_allow_html=True)

if market_rankings: st.info(f"🟢 **全市場 RS 資料庫已就緒** ｜ 收錄 **{len(market_rankings)}** 檔台股 ｜ 狀態：{db_status}")
else: st.warning("🟡 正在等待全市場 RS 排名資料載入...")

tab_portfolio, tab_leaderboard = st.tabs(["📈 個人持倉風控監控", "🏆 全市場 RS 排行榜 & 萬用個股查詢"])

# ==========================================
# 分頁 1：個人持倉風控監控儀表板
# ==========================================
with tab_portfolio:
    with st.expander("⚙️ 風控與動能參數設定", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            stop_loss_pct = st.number_input("🔴 初始停損趴數 (%)", min_value=1.0, value=7.0, step=0.5, format="%.1f")
            breakeven_trigger_pct = st.number_input("🛡️ 保本停損啟動門檻 (%)", min_value=1.0, value=8.0, step=0.5, format="%.1f")
            pyramid_safety_margin = st.number_input("⚖️ 加碼安全邊際 (%)", min_value=0.5, value=4.0, step=0.5, format="%.1f")
        with c2:
            pullback_target_pct = st.number_input("🟣 高點回檔停利趴數 (%)", min_value=1.0, value=10.0, step=0.5, format="%.1f")
            bias_threshold = st.number_input("🟠 月線正乖離過熱閥值 (%)", min_value=5.0, value=30.0, step=1.0, format="%.0f")
        with c3:
            time_stop_days = st.number_input("⏳ 時間停損天數（天）", min_value=1, value=10, step=1)
            discount_display = st.number_input("💰 券商手續費折數", min_value=0.01, value=0.60, step=0.05, format="%.2f")

    portfolio = load_data()

    with st.expander("➕ 新增持股 / 建倉", expanded=False):
        with st.form("add_stock_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                sym = st.text_input("股票代號", placeholder="例如: 2330")
                name = st.text_input("股票名稱", placeholder="例如: 台積電")
            with col2:
                mkt = st.selectbox("市場別", ["TW (上市)", "TWO (上櫃)"])
                entry_d = st.date_input("進場日期", value=get_tw_now().date())
            with col3:
                price = st.number_input("買進價格", min_value=0.1, step=0.1, value=100.0)
                shs = st.number_input("買進股數", min_value=1, step=1000, value=1000)
                
            if st.form_submit_button("確認建立持倉") and sym:
                new_item = {
                    "symbol": sym.strip(),
                    "name": clean_stock_name(name.strip(), sym.strip()),
                    "market": "TWO" if "TWO" in mkt else "TW",
                    "entry_date": str(entry_d),
                    "avg_cost": price,
                    "shares": int(shs),
                    "record_high": price,
                    "realized_pnl": 0,
                    "history": [{"時間": get_tw_now_str("%Y-%m-%d %H:%M"), "動作": "🌱 初始建倉", "成交價": price, "異動股數": f"+{int(shs)}", "剩餘股數": int(shs), "單筆實現損益": "0 元", "備註": f"起始成本 ${price}"}]
                }
                portfolio.append(new_item)
                save_data(portfolio)
                st.success(f"已新增 {new_item['name']} ({sym})")
                st.rerun()

    if not portfolio: st.info("目前尚無持倉，請點擊上方「➕ 新增持股」建立第一檔股票。")
    else:
        rf_col1, rf_col2 = st.columns([1, 4])
        with rf_col1:
            if st.button("🔄 刷新最新市價", use_container_width=True):
                st.cache_data.clear()
                st.session_state.last_portfolio_refresh = get_tw_now_str()
                st.rerun()
        with rf_col2: st.success(f"🕒 **台灣時間（最新更新）：{st.session_state.last_portfolio_refresh}**")

        for idx, item in enumerate(portfolio):
            sym, mkt, entry_d = item["symbol"], item["market"], item["entry_date"]
            name = clean_stock_name(item.get("name", sym), sym)
            avg_cost, shares = item["avg_cost"], item["shares"]
            stored_high, realized_pnl = item.get("record_high", avg_cost), item.get("realized_pnl", 0)
            
            info = get_stock_rs_info(sym, market_rankings)
            rs_score = info.get("rs_rating", 50) if info else 50
            
            cur_price, max_high, ma20, r_5d, r_1m, r_1q = fetch_stock_and_momentum(sym, mkt, entry_d)
            cur_price, max_high, ma20 = cur_price or avg_cost, max_high or stored_high, ma20 or avg_cost

            actual_high = max(stored_high, avg_cost, max_high)
            if actual_high != stored_high:
                portfolio[idx]["record_high"] = actual_high
                save_data(portfolio)

            net_pnl, roi, breakeven_p = calc_pnl(shares, avg_cost, cur_price, discount_display)
            pullback_pct = round(((actual_high - cur_price) / actual_high) * 100, 1) if actual_high > 0 else 0
            bias_20 = round(((cur_price - ma20) / ma20) * 100, 1) if ma20 > 0 else 0
            days_held = (get_tw_now().date() - datetime.strptime(entry_d, "%Y-%m-%d").date()).days

            status_badge = get_trend_master_status(info or {"rs_rating": rs_score, "pattern_badge": "", "r_5d": r_5d})

            is_be = ((actual_high - avg_cost) / avg_cost) * 100 >= breakeven_trigger_pct
            init_stop = round(avg_cost * (1 - stop_loss_pct / 100), 2)
            eff_stop = max(init_stop, breakeven_p) if is_be else init_stop
            pb_price = round(actual_high * (1 - pullback_target_pct / 100), 2)

            s_txt, s_col = "⚪ 持股續抱中", "gray"
            if cur_price <= eff_stop:
                s_txt, s_col = (f"🛡️ 觸發保本出場線（{eff_stop} 元）！強制保護本金零虧損出場", "red") if is_be else (f"🔴 觸發 -{stop_loss_pct}% 停損線（{eff_stop} 元）！全數出場", "red")
            elif cur_price <= pb_price and cur_price > avg_cost: s_txt, s_col = f"🟣 觸發高點回檔 {pullback_target_pct}%（跌破 {pb_price} 元）！建議減碼", "purple"
            elif bias_20 >= bias_threshold: s_txt, s_col = f"🟠 月線正乖離達 {bias_20}%（過熱）！建議減碼", "orange"
            elif days_held >= time_stop_days and abs(roi) <= 2.0: s_txt, s_col = f"⏳ 觸發時間停損（持股已 {days_held} 天，動能停滯）！建議換股", "orange"

            with st.container():
                st.markdown("---")
                st.subheader(f"{name} ({sym}.{mkt}) ｜ 📦 剩餘: {shares:,} 股 ｜ 持有 {days_held} 天 ｜ {status_badge}")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("近 5 日累積動能", f"{r_5d:+}%")
                m2.metric("近 1 個月累積動能", f"{r_1m:+}%")
                m3.metric("近 1 季累積動能", f"{r_1q:+}%")
                m4.metric("全市場 RS Rating", f"{rs_score} 分")

                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("剩餘持股 / 均價", f"{shares:,} 股", f"均價: ${avg_cost}")
                c2.metric("最新市價", f"${cur_price}", f"高點回檔: -{pullback_pct}%")
                c3.metric("未實現損益", f"{net_pnl:+,} 元", f"{roi:+}%")
                c4.metric("累積已實現損益", f"{realized_pnl:+,} 元")
                c5.metric("🛡️ 保本停損線" if is_be else f"🔴 初始停損 (-{stop_loss_pct}%)", f"${eff_stop}", f"回檔價: ${pb_price}")

                st.markdown(f"**風控狀態：** :{s_col}[{s_txt}]")

                with st.expander(f"⚙️ 操作 {name}（加碼 / 減碼 / 結清）"):
                    op1, op2, op3 = st.columns(3)
                    with op1:
                        st.write("##### 🔼 順勢金字塔加碼")
                        add_p = st.number_input("加碼價格", min_value=0.1, value=cur_price, key=f"ap_{idx}")
                        add_s = st.number_input("加碼股數", min_value=1, step=1000, value=1000, key=f"as_{idx}")
                        sim_avg = round(((shares * avg_cost) + (int(add_s) * add_p)) / (shares + int(add_s)), 2)
                        buf = round(((cur_price - sim_avg) / cur_price) * 100, 1)
                        st.caption(f"試算新均價：**${sim_avg}** ｜ 安全緩衝：**{buf:+}%**")
                        
                        if st.button("確認加碼", key=f"ba_{idx}"):
                            portfolio[idx]["history"].append({"時間": get_tw_now_str("%Y-%m-%d %H:%M"), "動作": "🔼 順勢加碼", "成交價": add_p, "異動股數": f"+{int(add_s)}", "剩餘股數": shares + int(add_s), "單筆實現損益": "-", "備註": f"新均價 ${sim_avg} (緩衝 {buf:+}%)"})
                            portfolio[idx]["shares"] += int(add_s)
                            portfolio[idx]["avg_cost"] = sim_avg
                            save_data(portfolio); st.rerun()

                    with op2:
                        st.write("##### 🔽 分批減碼")
                        red_p = st.number_input("減碼價格", min_value=0.1, value=cur_price, key=f"rp_{idx}")
                        red_s = st.number_input("減碼股數", min_value=1, max_value=shares, step=1000, value=min(1000, shares), key=f"rs_{idx}")
                        sim_pnl, sim_roi, _ = calc_pnl(int(red_s), avg_cost, red_p, discount_display)
                        st.caption(f"試算本次實現損益：**{sim_pnl:+,} 元** ({sim_roi:+}%)")
                        
                        if st.button("確認減碼", key=f"br_{idx}"):
                            new_shares = shares - int(red_s)
                            portfolio[idx]["history"].append({"時間": get_tw_now_str("%Y-%m-%d %H:%M"), "動作": "🔽 分批減碼", "成交價": red_p, "異動股數": f"-{int(red_s)}", "剩餘股數": new_shares, "單筆實現損益": f"{sim_pnl:+,} 元", "備註": f"報酬率 {sim_roi:+}%"})
                            if new_shares > 0:
                                portfolio[idx]["shares"] = new_shares
                                portfolio[idx]["realized_pnl"] = realized_pnl + sim_pnl
                            else: portfolio.pop(idx)
                            save_data(portfolio); st.rerun()

                    with op3:
                        st.write("##### 🗑️ 結清出場")
                        if st.button("結清持倉", key=f"bd_{idx}"):
                            portfolio.pop(idx)
                            save_data(portfolio); st.rerun()

                if item.get("history"):
                    with st.expander(f"📜 {name} 交易歷程 (剩餘 {shares:,} 股)", expanded=False):
                        st.dataframe(pd.DataFrame(item["history"]), use_container_width=True, hide_index=True)

# ==========================================
# 分頁 2：全市場 RS 排行榜與個股查詢
# ==========================================
with tab_leaderboard:
    st.subheader("🔍 萬用個股 RS 評分查詢")
    sq1, sq2 = st.columns([3, 1])
    search_query = sq1.text_input("輸入股票代號或名稱查詢（例如：2330、聯一光、3441）", placeholder="請輸入代號或名稱...").strip().upper()
    
    if search_query:
        matched = [m for m in market_rankings if search_query in str(m.get("symbol", "")) or search_query in str(m.get("name", "")).upper()]
        if matched:
            st.write(f"找到 **{len(matched)}** 筆符合標的：")
            for m in matched:
                score, m_type, sym, raw_score = m.get("rs_rating", 50), m.get("market", "台股"), m.get("symbol"), m.get("score", 0.0)
                name = clean_stock_name(m.get("name"), sym)
                
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("標的", f"{name} ({sym})", m_type)
                r2.metric("RS Rating 評分", f"{score} 分", get_trend_master_status(m))
                r3.metric("綜合動能得分", f"{raw_score:+.2f}")
                r4.metric("全市場地位", f"贏過全台 {score}% 股票")
                st.markdown("---")
        else: st.error(f"查無符合「{search_query}」的標的。")

    st.subheader("🏆 全市場 RS 領袖股強勢排行榜")
    df_raw = pd.DataFrame(market_rankings)
    if not df_raw.empty:
        f1, f2 = st.columns([1, 3])
        min_rs = f1.number_input("最低 RS 門檻篩選", min_value=1, max_value=99, value=75, step=1)
        market_filter = f2.multiselect("市場別篩選", ["上市", "上櫃"], default=["上市", "上櫃"])

        df = df_raw[(df_raw["rs_rating"] >= min_rs) & (df_raw["market"].isin(market_filter))].copy()
        df["name"] = df.apply(lambda r: clean_stock_name(r.get("name"), r.get("symbol")), axis=1)
        df["順勢操作狀態"] = df.apply(get_trend_master_status, axis=1)
        df = df.sort_values(by="rs_rating", ascending=False)[["rs_rating", "symbol", "name", "market", "score", "順勢操作狀態"]]
        df.columns = ["RS 評分 (PR)", "股票代碼", "中文名稱", "上市櫃", "綜合動能得分", "順勢操作狀態"]

        st.caption(f"共計 **{len(df)}** 檔標的符合條件（RS ≥ {min_rs}）：")
        st.dataframe(df, use_container_width=True, hide_index=True, height=500)
    else: st.info("尚無排名資料，請先執行排程產生資料。")
