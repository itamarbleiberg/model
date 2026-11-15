# Ninjago Time Blades – Resource Pack ל-Minecraft Java 1.21.11

חבילת Resource Pack שמוסיפה **חמישה להבי זמן תלת־ממדיים** בהשראת Ninjago, כפריטים נפרדים עם מודל, טקסטורות ואנימציה משלהם.
העיצוב מקורי (נבנה מחדש מאפס בהשראת התמונות), ואינו העתק של מודל רשמי או של חלק LEGO.

## מה יש בחבילה

| # | להב | מזהה (item_model) | צבע / אנרגיה | אנימציה |
|---|-----|-------------------|--------------|----------|
| 1 | Basic Time Blade | `timeblades:basic_time_blade` | גוף ברונזה, כתר ושרוול נחושת, להבי כסף, ניצוצות זהב עדינים | ברק זהוב, ברק כסוף שזורם לאט |
| 2 | Forward Time Blade | `timeblades:forward_time_blade` | ירוק | גלי אנרגיה רצים במהירות **לכיוון הקצוות** |
| 3 | Slow-Mo Time Blade | `timeblades:slowmo_time_blade` | כחול | אותה זרימה **בהילוך איטי**, ברקים איטיים |
| 4 | Pause Time Blade | `timeblades:pause_time_blade` | אדום | פעימה אחת ואז **קפיאה**; הברקים נעצרים ומתחילים שוב |
| 5 | Reversal Time Blade | `timeblades:reversal_time_blade` | כתום/ענבר | האנרגיה זורמת **אחורה** אל הידית, והברקים מתנגנים הפוך |

לכל להב:
* מודל תלת־ממדי מלא (כ־650 אלמנטים): שני להבי קרן מעוקלים בצורת U שמתחברים מתחת לגוף, גוף אובלי משוריין משכבות לוחות חופפות בצורת V עם רכס מרכזי וניטים, כתר של שלושה לוחות מחודדים, צוואר, שרוול אחיזה עם שוליים, וגב עם סמל שעון חול חרוט.
* שלוש טקסטורות עם UV ייחודי לכל פאה: `*_body.png` (מתכת, 256×576), `*_blade.png` (להב מונפש, 16 פריימים), `*_energy.png` (ברקים מונפשים, 12 פריימים).
* הלהבים והברקים זוהרים בחושך (`light_emission: 15`), חוץ מלהבי הכסף של ה-Basic.
* הגדרות תצוגה ליד ראשונה (ימין ושמאל), יד שלישית, אינבנטורי, קרקע, מסגרת פריט, מדף וראש.

## התקנה

1. הורידו את `NinjagoTimeBlades_1.21.11.zip` (אל תחלצו אותו).
2. פתחו את Minecraft Java 1.21.11 ← **Options… ← Resource Packs… ← Open Pack Folder**.
3. העתיקו את קובץ ה-ZIP לתיקייה שנפתחה (`.minecraft/resourcepacks`).
4. חזרו למשחק, העבירו את **Ninjago Time Blades** לרשימת החבילות הפעילות ולחצו **Done**.

## שימוש

הפריטים מופעלים דרך ה-component ‏`minecraft:item_model`, כך שלא צריך מודים או Data Pack.
בעולם עם cheats (או כ-op) הדביקו בצ'אט אחת מהפקודות שב-`commands.txt`, למשל:

```
/give @s netherite_sword[item_model="timeblades:forward_time_blade",item_name={"text":"Forward Time Blade","color":"green"}]
```

* בבלוק פקודה החליפו `@s` ב-`@p`.
* הפריט הבסיסי הוא חרב נתרייט שלא נשברת, כך שהלהב גם פוגע כמו חרב. אפשר להחליף אותו בכל פריט אחר; המראה נקבע רק לפי `item_model`.
* כל הפקודות קצרות מ-256 תווים, כך שאפשר להדביק אותן ישירות בצ'אט.

## מבנה הקבצים

```
NinjagoTimeBlades/
├── pack.mcmeta              (min_format / max_format = 75 → 1.21.11)
├── pack.png
├── README.md
├── commands.txt
└── assets/timeblades/
    ├── items/               5 הגדרות פריט (מערכת Item Models)
    ├── models/item/         5 מודלים תלת־ממדיים
    └── textures/item/time_blade/
        ├── <blade>_body.png
        ├── <blade>_blade.png   + .png.mcmeta (אנימציה)
        └── <blade>_energy.png  + .png.mcmeta (אנימציה)
```

## הערות טכניות

* תואם **רק** ל-Java 1.21.11 (resource pack format 75). המודלים משתמשים בסיבוב אלמנטים בכמה צירים ובזוויות חופשיות, שנוספו בגרסה 1.21.11. בגרסאות ישנות יותר הם לא ייטענו נכון.
* כל הטקסטורות נמצאות תחת `textures/item`, כלומר באטלס הפריטים. ב-1.21.11 מודל פריט לא יכול לערבב טקסטורות משני אטלסים.
* שקיפות הברקים עובדת באופן רגיל, כי פריטים מצוירים ב-translucent item sheet. אין צורך ב-OptiFine או בשיידרים.
* את האנימציות אפשר לראות ב-`previews/anim_*.gif`, ואת התצוגה ביד ובאינבנטורי ב-`previews/in_hand_*.png` וב-`previews/hotbar_gui.png`.

## בנייה מחדש (למתקדמים)

כל החבילה נוצרת באופן פרוצדורלי מקוד Python שבתיקייה `tools/` (גיאומטריה, UV, אפייה של טקסטורות, תצוגה מקדימה ובדיקות):

```
tools/run.sh tools/build.py        # מודלים + טקסטורות
tools/run.sh tools/packfiles.py    # pack.mcmeta, README, commands
tools/run.sh tools/validate.py     # בדיקות תקינות
tools/run.sh tools/preview.py all previews
```

## קרדיט

חבילת מעריצים לא רשמית. Ninjago ו-LEGO הם סימנים מסחריים של LEGO Group, והחבילה אינה קשורה אליהם. המודלים והטקסטורות נוצרו במיוחד עבור החבילה הזו.
