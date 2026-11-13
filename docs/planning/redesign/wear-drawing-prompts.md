# 怎麼戴上、拿下：線條圖生圖敘述（#503）

給 GPT 生圖用。依照本人 2026-11-13 審圖的意見調整成 **18 張**：
- 「開機」「關機收好」改成耳掛型、耳內型各一張，每張分左右兩格（裝電池的／充電的），不再三型共用。
- 耳掛的兩型（有耳模、耳塞和細線）機身一樣，這兩張共用。

## 怎麼用

1. 先貼「共同畫風」，再一張一張貼各圖的 Prompt。18 張都在同一個對話裡生，畫風比較一致。
2. 每張生完先看「畫面」那一欄，對不對再存。檔名用代碼，例如 `wear_left_right.png`。
3. 方向的約定：耳朵都畫**右耳、從側面看、臉朝畫面右邊**。所以「往後」是往畫面左邊，「往前」是往畫面右邊。

## 共同畫風

**中文**：給長輩看的衛教步驟圖。只用兩個顏色：深藍線條、淺藍填色，白底。沒有陰影、漸層、寫實膚色，也沒有文字和品牌。線條圓頭、粗細適中。橫式 3:2，主體大、置中、四周留白。箭頭是細線加實心三角形箭頭。手只畫從畫面右邊伸進來的拇指和食指。

```
Simple instructional line illustration for a health leaflet for elderly readers.
Two colors only: dark blue outlines (#1F4E8C) and flat light blue fill (#E7EEF8) inside shapes, on a plain white background.
No shading, no gradients, no realistic skin color, no shadows, no text, no brand logos, no numbers.
Clean rounded strokes of medium weight, few details, friendly and calm.
Landscape 3:2 (1200x800). Subject large and centered with generous margins.
Arrows: thin line with a solid triangular arrowhead, same dark blue.
Hands: show only a thumb and an index finger coming in from the right edge, simple outline.
Ears: always a RIGHT ear seen from the side, the person's face is toward the right edge of the image.
Keep exactly the same style for every image in this set.
```

---

## 1. `wear_left_right`：分左右（三型共用）

- 用在：三型・戴上 1. 分左右
- 畫面：長輩的後腦和肩膀，從背後看。頭髮蓋住整個後腦，一看就是背面、沒有臉。畫面右邊（本人的右耳）旁一個紅色實心圓點，下面寫「右」；左邊旁一個藍色實心圓點，下面寫「左」。整張只有這兩個字。

```
The back of an elderly person's head and shoulders, seen from behind. Short hair covers the whole back of the head so it is clearly the back (no face visible). Both ears visible.
A solid red dot (#C62828) next to the ear on the RIGHT side of the image, with the Chinese character 右 under it.
A solid dark blue dot (#1F4E8C) next to the ear on the LEFT side of the image, with the Chinese character 左 under it.
These two characters are the only text in the image.
```

## 2. `behind_ear_switch_on`：開機（耳掛兩型共用）

- 用在：耳掛（有耳模）、耳掛（耳塞和細線）・戴上 2. 開機
- 畫面：左右兩格，中間留一條細縫。左格「裝電池的」：耳掛型機身（彎彎的香蕉形）側面，底部的電池門打開、裡面有一顆圓形鈕扣電池，彎箭頭表示把門關上。右格「充電的」：同一個機身，食指指尖按住機身上的按鍵，旁邊三道小弧線表示「按住幾秒」。不畫耳朵。

```
Two panels side by side with a thin gap between them. No ear in this image.
Left panel: a behind-the-ear hearing aid body (curved, banana-shaped) seen from the side. The small battery door at its bottom is swung open, a round button battery sits in it, and a curved arrow shows the door being closed.
Right panel: the same behind-the-ear hearing aid. An index fingertip presses and holds the push button on the aid; three small curved lines next to the fingertip mean "hold for a few seconds".
```

## 3. `in_ear_switch_on`：開機（耳內）

- 用在：耳內・戴上 2. 開機
- 畫面：同上兩格，換成耳內型（訂做外殼）從面板那一面看。左格：面板上的電池門打開、有電池，箭頭關門。右格：指尖按住面板上的小按鍵，旁邊三道小弧線。

```
Two panels side by side with a thin gap. No ear in this image.
Left panel: an in-the-ear hearing aid (custom-made shell) seen from its faceplate. The battery door on the faceplate is open with a round button battery inside; a curved arrow shows the door being closed.
Right panel: the same in-the-ear hearing aid; an index fingertip presses and holds the small button on the faceplate, with three small curved lines meaning "hold for a few seconds".
```

## 4. `behind_ear_put_away`：關機收好（耳掛兩型共用）

- 用在：耳掛（有耳模）・拿下 3.、耳掛（耳塞和細線）・拿下 4. 關機收好
- 畫面：左右兩格。左格「裝電池的」：打開的硬殼收納盒，兩個耳掛型助聽器放在裡面，電池門都打開。右格「充電的」：打開的充電座，有兩個孔位；一個耳掛型助聽器已經插在孔裡，另一個正往下插進另一個孔，向下的箭頭。

```
Two panels side by side with a thin gap.
Left panel: an open hard clamshell storage case with two behind-the-ear hearing aids lying inside; their battery doors are open.
Right panel: an open hearing aid charging case with two slots. One behind-the-ear hearing aid already stands in its slot; the other is being lowered into the second slot, with a downward arrow.
```

## 5. `in_ear_put_away`：關機收好（耳內）

- 用在：耳內・拿下 2. 關機收好
- 畫面：同上兩格，換成耳內型助聽器。

```
Two panels side by side with a thin gap.
Left panel: an open hard clamshell storage case with two in-the-ear hearing aids (custom shells) inside; their battery doors on the faceplates are open.
Right panel: an open charging case with two round slots. One in-the-ear hearing aid already sits in its slot; the other is being lowered into the second slot, with a downward arrow.
```

## 6. `behind_ear_mould_twist_in`：耳模轉進去

- 用在：耳掛（有耳模）・戴上 3. 耳模轉進去
- 畫面：右耳側面。拇指和食指從右邊捏著耳模，耳模伸進耳道的那一小截對準耳道口。耳模的形狀：填滿耳殼凹處的軟塑膠塊，有一小截伸進耳道，上方有一個小耳鉤；透明導管從耳模頂端往上延伸出畫面（看不到機身）。耳模下方一個彎箭頭，表示輕輕轉著推進去。

```
A right ear seen from the side (face toward the right edge).
A custom earmould is held between a thumb and index finger coming from the right. The earmould is a soft plastic piece shaped to fill the bowl of the ear, with a short stem that goes into the ear canal and a small arm on top; clear tubing comes out of its top and goes up out of the frame (the hearing aid body is not shown).
The earmould's stem is lined up right at the ear canal opening. A curved arrow under the earmould shows a gentle twist while pushing it in.
```

## 7. `behind_ear_mould_hook_on`：機身掛到耳後

- 用在：耳掛（有耳模）・戴上 4. 機身掛到耳後
- 畫面：右耳側面，耳模已經在耳殼凹處裡。導管從耳模頂端往上，繞過耳朵上方前面，接到耳鉤，耳鉤連著機身。機身是彎的，**內弧貼著耳殼後緣**，正放到耳朵後面；耳朵後面一個向下的彎箭頭。

```
A right ear seen from the side (face toward the right edge). The earmould is already seated in the bowl of the ear.
Clear tubing goes from the top of the earmould up and over the top front of the ear to the earhook of a behind-the-ear hearing aid.
The hearing aid body is curved and its inner curve follows the back edge of the ear closely; it is being placed down behind the ear. A downward curved arrow behind the ear shows this.
```

## 8. `behind_ear_mould_lift_off`：先拿下機身

- 用在：耳掛（有耳模）・拿下 1. 先拿下機身
- 畫面：跟圖 7 同一個場景，但箭頭向上：耳模還在耳朵裡，先把機身從耳朵後面往上拿起來。

```
Same scene as the previous image (right ear, earmould still seated in the ear, tubing over the top of the ear to the hearing aid body behind the ear),
but the curved arrow behind the ear points UP: the hearing aid body is being lifted up and off from behind the ear first, while the earmould stays in the ear.
```

## 9. `behind_ear_mould_twist_out`：轉出耳模

- 用在：耳掛（有耳模）・拿下 2. 轉出耳模
- 畫面：右耳側面。拇指和食指捏著**耳模本身**（不是導管），耳模正離開耳道；耳模下方彎箭頭表示轉著拿出來。導管上一個小「×」，表示不要拉導管。

```
A right ear seen from the side (face toward the right edge).
A thumb and index finger from the right hold the earmould itself (not the tubing) and the earmould is coming out of the ear. A curved arrow under it shows twisting it out.
A small "X" mark on the tubing above the earmould means "do not pull the tubing".
```

## 10. `behind_ear_dome_hook_on`：先掛機身（耳塞和細線）

- 用在：耳掛（耳塞和細線）・戴上 3. 先掛機身
- 畫面：右耳側面。細長的耳掛機身正放到耳朵後面，內弧貼著耳殼後緣；耳朵後面向下的彎箭頭。一條細線從機身頂端繞過耳朵上方，垂在耳朵前面、耳垂旁，末端是小小的收音管和軟矽膠耳塞（傘形，圓頭朝下、朝遠離細線的方向；細線接在收音管的尾端）。

```
A right ear seen from the side (face toward the right edge).
A slim receiver-in-canal hearing aid body is being placed behind the ear, its inner curve following the back edge of the ear; a downward curved arrow behind the ear.
A thin wire runs from the top of the body over the top of the ear and hangs down in front of the ear, beside the earlobe. At its end is a small receiver with a soft silicone dome (umbrella-shaped). The wire enters the BACK end of the receiver; the dome's rounded tip points away from the wire (downward).
```

## 11. `behind_ear_dome_push_in`：推進耳塞

- 用在：耳掛（耳塞和細線）・戴上 4. 推進耳塞
- 畫面：機身已經在耳後。拇指和食指捏著細線靠近耳塞的地方（收音管尾端），把耳塞推進耳道；耳塞的圓頭朝耳道。細線貼著頭的側邊、在耳朵前面。箭頭指向耳道。

```
A right ear seen from the side (face toward the right edge). The hearing aid body already sits behind the ear.
A thumb and index finger pinch the thin wire right where it joins the back of the receiver, and push the dome into the ear canal. The dome's rounded tip points into the canal.
The thin wire lies flat against the side of the head in front of the ear. An arrow points toward the ear canal.
```

## 12. `behind_ear_dome_tuck_line`：塞好固定線

- 用在：耳掛（耳塞和細線）・戴上 5. 塞好固定線
- 畫面：耳塞已經在耳道裡。收音管上有一條短短的透明固定線，正被塞進耳殼下方的凹處；箭頭指向凹處。

```
A right ear seen from the side (face toward the right edge). The dome is already inside the ear canal, the wire runs up over the ear to the body behind it.
A short clear retention line (a small tail) comes out of the receiver at the ear canal opening and is being tucked into the lower bowl of the ear. An arrow points into the bowl.
```

## 13. `behind_ear_dome_untuck_line`：拉出固定線

- 用在：耳掛（耳塞和細線）・拿下 1. 拉出固定線
- 畫面：跟圖 12 一樣，但固定線正從耳殼凹處被拉出來，箭頭朝外（畫面右下）。

```
Same scene as the previous image, but the short clear retention line is being pulled out of the bowl of the ear. An arrow points outward, away from the ear (toward the lower right).
```

## 14. `behind_ear_dome_pull_out`：拉出耳塞

- 用在：耳掛（耳塞和細線）・拿下 2. 拉出耳塞
- 畫面：機身還在耳後。拇指和食指捏著細線靠近耳塞的地方，把耳塞從耳道拉出來；箭頭朝外。耳朵上方的細線（離耳塞遠的那段）上一個小「×」，表示不要拉那裡。

```
A right ear seen from the side (face toward the right edge). The body is still behind the ear.
A thumb and index finger pinch the thin wire right next to the receiver and pull the dome out of the ear canal; an arrow points outward, away from the ear.
A small "X" mark on the wire near the top of the ear (far from the dome) means "do not pull here".
```

## 15. `behind_ear_dome_lift_off`：拿下機身

- 用在：耳掛（耳塞和細線）・拿下 3. 拿下機身
- 畫面：耳塞已經拿出來，垂在耳朵前面。機身正從耳朵後面往上拿起來，耳朵後面向上的彎箭頭。

```
A right ear seen from the side (face toward the right edge). The dome is already out of the ear and hangs on its wire in front of the ear.
The slim hearing aid body is being lifted up and off from behind the ear; an upward curved arrow behind the ear.
```

## 16. `in_ear_line_up`：對準耳道

- 用在：耳內・戴上 3. 對準耳道
- 畫面：右耳側面。拇指和食指在耳朵右邊捏著耳內型助聽器（訂做外殼），出聲的那一端朝耳道；外殼上的小拉線朝下、朝後（畫面左下）。箭頭指向耳道。

```
A right ear seen from the side (face toward the right edge).
To the right of the ear, a thumb and index finger hold an in-the-ear hearing aid (custom-made shell). Its sound outlet end points toward the ear canal; the small removal cord on the shell points downward and backward (toward the lower left).
An arrow points toward the ear canal.
```

## 17. `in_ear_twist_in`：轉著推進去

- 用在：耳內・戴上 4. 轉著推進去
- 畫面：耳內型助聽器正被手指轉著推進耳朵（彎箭頭表示轉動）。另一隻手的指尖在耳朵上緣，把耳朵往後上輕拉；耳朵上方一個朝左上的箭頭。

```
A right ear seen from the side (face toward the right edge).
A thumb and index finger push an in-the-ear hearing aid into the ear with a gentle twist (curved arrow around the hearing aid).
A fingertip of the other hand gently pulls the top of the ear up and back; an arrow at the top of the ear points up and to the left.
```

## 18. `in_ear_twist_out`：轉出來

- 用在：耳內・拿下 1. 轉出來
- 畫面：拇指和食指捏著耳內型助聽器的拉線（或外殼邊緣），彎箭頭表示轉動，直箭頭朝外表示拿出來。

```
A right ear seen from the side (face toward the right edge).
A thumb and index finger pinch the small removal cord (or the edge of the shell) of an in-the-ear hearing aid and twist it out of the ear: a curved arrow shows the twist and a straight arrow points outward, away from the ear.
```

---

## 生完之後要注意

- **畫風**：#502 寫線條圖「畫風、線寬、尺寸照日常保養」。生出來的圖跟保養的 9 張放在同一頁，差太多的話，保養那 9 張也要重生或改回手畫。
- **檔案**：生出來是 PNG 圖片，不是現在的 SVG；顏色寫死在圖裡，以後改主色要重生。每張壓到 100 KB 以內，用 `alt=""` 讓讀螢幕軟體跳過。
- **授權**：用之前確認生圖服務的使用條款允許放在網站上。
- **字句**：圖 2–5 改成兩格之後，「開機」「關機收好」的字句也要分兩種寫（裝電池的／充電的），逐句審時一起定。
