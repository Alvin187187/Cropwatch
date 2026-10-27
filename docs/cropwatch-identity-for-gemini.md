# CROPWATCH identity guide for Gemini

Paste **Master lock** before every prompt. Generate **one asset per turn**. If a sheet comes back with wrong colors, extra text, or a different plant, regenerate that item from its single prompt.

Official wordmark is `CROPWATCH`, all capitals. The product line is: **See where the rice is at risk.** The limit line is: **Favorable conditions, not a diagnosis.**

CROPWATCH is a decision-support map for rice pest and disease **conditions** in Nueva Ecija. It shows where to look. It does not say a pest is present, and it does not estimate pesos or yield loss.

Audience: provincial agriculture office, municipal agriculture staff, field inspection teams.

---

## Colors

Use these hex values exactly. Do not invent a brighter green.

### Brand

| Role | Name | Hex | RGB | Use |
| --- | --- | --- | --- | --- |
| Background | Paper | `#F4EDE6` | 244, 237, 230 | Screens, light logo field, icon backgrounds |
| Background alt | Paper warm | `#F7F1E8` | 247, 241, 232 | Cards, panels |
| Field | Black | `#000000` | 0, 0, 0 | Dark half of the brand, dark logo field |
| Ink | Olive | `#404F1D` | 64, 79, 29 | Wordmark, logo mark, icon stroke, buttons |
| Ink deep | Deep olive | `#2C3816` | 44, 56, 22 | Pressed states, dark olive type |
| Secondary text | Muted olive | `#4E5A32` | 78, 90, 50 | Captions, meta |
| Secondary | Sage | `#7C914D` | 124, 145, 77 | Hover, secondary marks, low-risk swatch |
| Hairline | Line | `#E6D9C8` | 230, 217, 200 | Rules, dividers |
| On black | Cream | `#F3EFE4` | 243, 239, 228 | Type and marks on black |
| On olive button | White | `#FFFFFF` | 255, 255, 255 | Label on an olive button |

### Risk — data only

These colors encode hazard class. They are not logo colors. Do not paint the wordmark red, orange, or gold.

| Class | Hex | RGB | Meaning in the product |
| --- | --- | --- | --- |
| Low | `#7C914D` | 124, 145, 77 | Low risk. Same sage as the brand secondary |
| Moderate | `#A67C1F` | 166, 124, 31 | Moderate risk |
| High | `#D05327` | 208, 83, 39 | High risk |
| Very high | `#DB2E27` | 219, 46, 39 | Very high risk |
| No data | `#B7B1A6` | 183, 177, 166 | Insufficient data. Stone, not gray-blue |

### Change — data only

| State | Hex | Use |
| --- | --- | --- |
| Increased | `#9F2D2D` | Score went up |
| New high | `#D4652F` | Newly high |
| Decreased | `#2D6A4F` | Score went down |
| Unchanged | `#D6D0C4` | No meaningful change |

### Map ramps — data only

Do not use these as brand colors. They belong on choropleth layers.

| Layer | Low → high |
| --- | --- |
| Rain, humidity, soil, leaf wetness, flood | `#F4EFE6` → `#8FB4C9` → `#1D5F8A` → `#16324F` |
| Temperature, surface temperature | `#2C5F7C` → `#D8C7A1` → `#D4652F` → `#9F2D2D` |
| Wind | `#F4EFE6` → `#C4B8A8` → `#6B5E52` → `#2A2622` |
| NDVI, EVI, rice area | `#C4A574` → `#A3B18A` → `#2D6A4F` → `#1B4332` |
| Elevation | `#E7F0D8` → `#C4B48A` → `#8A6A45` → `#3D342C` |
| Priority | `#EFE6D6` → `#C4B48A` → `#C45C28` → `#8E2424` |

### Color rules

- Logo ink on paper is olive `#404F1D`. Logo ink on black is cream `#F3EFE4`.
- Sage `#7C914D` is the only bright green. No lime, no `#00A651`, no emerald gradient.
- One risk color per icon. A threat icon stays olive. A risk icon uses its class color.
- Panels are square. Buttons and inputs are pills. Icons are not pills.
- No gradients, foil, glow, or drop shadow on logo or icons.

---

## Master lock

Paste this above every prompt.

```
CROPWATCH visual system for a public rice-risk map in Nueva Ecija, Philippines. Quiet, editorial, precise. Flat vector, like a printed field manual. Paper #F4EDE6, black #000000, olive ink #404F1D, deep olive #2C3816, sage #7C914D, line #E6D9C8, cream #F3EFE4. Risk colors only when the prompt names a risk class: low #7C914D, moderate #A67C1F, high #D05327, very high #DB2E27, no data #B7B1A6.

The official mark is one rice tiller: a horizontal ground line, a straight vertical stem, two upper leaves curving up and outward, two shorter lower leaves. Uniform stroke, round caps, no fill, no extra outline, no grains, no roots, no sun.

If text is required, the only word is CROPWATCH in Helvetica Neue Medium, all capitals, tight tracking. No tagline unless the prompt asks.

No 3D, no gloss, no gradient, no neon, no cartoon, no robot, no sparkles, no circuit, no magnifying glass, no leaf-plus-wifi, no drone in the logo, no Philippine flag, no skull, no biohazard mark, no smiling farmer, no photoreal insect inside a symbol.
```

---

## Drawing rules

Icons and the logo mark share one stroke.

- Grid: 24 × 24. Keep artwork inside a 20 × 20 live area.
- Stroke: 1.6, round caps, round joins. No fill, except risk swatches and solid map markers.
- Optical padding: equal on all sides. Center the symbol.
- Corners of symbols are slightly curved from the stroke cap, not from a rounded rectangle container.
- One metaphor per icon. A blast icon is a leaf lesion. A planthopper icon is a side-view hopper. Do not combine them with a map pin.
- Threat icons describe the organism or symptom. They do not mean “this pest is here.”
- Alert icons mean “look here” or “score changed.” They do not mean outbreak, infection confirmed, or crop lost.
- Export idea: 1024 × 1024 PNG, symbol centered, background as specified. Logos at 2048 px wide.

---

## 1. Primary logo

Horizontal lockup is the primary logo: tiller mark at left, wordmark at right, vertically centered. Gap between mark and word equals the stem height. Clear space on every side equals the stem height. Smallest use: mark 16 px tall, wordmark cap height 14 px.

```
Primary CROPWATCH logo, horizontal lockup, on paper #F4EDE6. Left: the rice tiller mark in olive #404F1D, stroke only. Right: the word CROPWATCH in Helvetica Neue Medium, all capitals, olive #404F1D, tight tracking, vertically centered with the mark. Wide clear space. Flat vector. No tagline, no shadow, no box, no second color.
```

---

## 2. Logo symbol / icon

The symbol is the tiller alone. This is the only logo mark. Do not design a second symbol.

Construction on a 24 grid: ground line from x 4 to 20 at y 18.5. Stem at x 12 from y 18.5 up to y 7.5. Upper leaf pair leaves the stem near y 12 and curves up. Lower leaf pair leaves the stem near y 15 and is shorter.

```
CROPWATCH logo symbol alone, centered on paper #F4EDE6. One rice tiller: horizontal ground line, vertical stem, two long upper leaves curving up and out, two shorter lower leaves. Olive #404F1D, uniform round stroke, no fill. Large padding. No text, no circle, no container.
```

---

## 3. Wordmark

```
The word CROPWATCH only, centered, Helvetica Neue Medium, all capitals, tight tracking, olive #404F1D on paper #F4EDE6. No symbol, no underline, no box, no shadow. Generous margin.
```

---

## 4. Horizontal logo lockup

Same as the primary logo. Use this prompt when regenerating the lockup without a tagline.

```
Horizontal CROPWATCH lockup on paper #F4EDE6. Tiller mark on the left, word CROPWATCH on the right, both olive #404F1D, vertically centered, clear gap. Helvetica Neue Medium, all caps, tight tracking. Flat vector, no tagline, no border.
```

With the place name, for documents:

```
Horizontal CROPWATCH lockup on paper #F4EDE6. Tiller mark left. To the right, two lines, left aligned: CROPWATCH in olive #404F1D, Helvetica Neue Medium, all caps, tight tracking. Under it, smaller: Nueva Ecija in muted olive #4E5A32, regular weight, not all caps. No other text.
```

---

## 5. Stacked logo lockup

```
Stacked CROPWATCH logo, centered on paper #F4EDE6. Tiller mark on top. Below it, centered, the word CROPWATCH in Helvetica Neue Medium, all capitals, tight tracking, olive #404F1D. Gap smaller than the mark. No tagline, no circle, no shadow.
```

---

## 6. Monochrome logo

One color only. Produce three files from these three prompts.

```
Monochrome CROPWATCH horizontal lockup. Tiller mark and the word CROPWATCH in a single olive #404F1D on paper #F4EDE6. No second color, no gray, no shadow.
```

```
Monochrome CROPWATCH horizontal lockup. Tiller mark and the word CROPWATCH in solid black #000000 on white #FFFFFF. No gray, no shadow.
```

```
Monochrome CROPWATCH horizontal lockup. Tiller mark and the word CROPWATCH in solid cream #F3EFE4 on black #000000. No gray, no shadow.
```

---

## 7. Dark background logo

```
CROPWATCH horizontal lockup on solid black #000000. Tiller mark and the word CROPWATCH in cream #F3EFE4. Helvetica Neue Medium, all caps, tight tracking. Flat. No glow, no green, no photograph behind it.
```

Symbol only:

```
CROPWATCH tiller mark only, cream #F3EFE4, centered on solid black #000000. Stroke only. No text, no glow.
```

---

## 8. Light background logo

```
CROPWATCH horizontal lockup on paper #F4EDE6. Tiller mark and the word CROPWATCH in olive #404F1D. Helvetica Neue Medium, all caps, tight tracking. Flat. No photograph, no texture, no border.
```

```
CROPWATCH tiller mark only, olive #404F1D, centered on paper #F4EDE6. Stroke only. No text.
```

---

## 9. App icon / favicon

The mark must read at 16 px. No wordmark. Square field. Keep the tiller inside the center 70%.

```
iOS app icon, squircle, solid paper #F4EDE6. Centered CROPWATCH tiller mark in olive #404F1D, stroke only, thick enough to read at small size. No letters, no shadow, no gloss, no photo.
```

```
App icon, square with slightly rounded corners, solid black #000000. Centered CROPWATCH tiller mark in cream #F3EFE4, stroke only. No letters, no glow.
```

```
Favicon, perfect square, paper #F4EDE6, one olive #404F1D tiller centered, very simple stroke, readable at 16 pixels. No text.
```

---

## 10. Social media profile icon

Same art as the app icon. Keep the tiller inside a center circle so a round crop does not cut the leaves.

```
Social profile image, square, black #000000. CROPWATCH tiller in cream #F3EFE4, centered, with enough padding that a circular crop still shows the whole plant and the ground line. No text, no photo, no border.
```

```
Social profile image, square, paper #F4EDE6. CROPWATCH tiller in olive #404F1D, centered, circular-crop safe. No text.
```

---

## 11. Rice crop glyph

Content icon for rice area and rice fraction. Related to the logo, but it is a plant study, not the official mark. No ground line bar.

```
Single icon, centered, paper #F4EDE6. A rice tiller in olive #404F1D stroke: vertical stem and four simple leaves, no ground line, no grains, no text. Same stroke weight as a UI icon. Large padding.
```

---

## 12. CROPWATCH monitoring glyph

Watching a field, not a security camera and not an eye logo.

```
Single icon, centered, paper #F4EDE6, olive #404F1D stroke. A square field divided into four paddies, with a short horizontal scan line across the middle. No eye, no camera, no person, no text.
```

---

## 13. Agricultural intelligence symbol

A score, not a brain.

```
Single icon, centered, paper #F4EDE6, olive #404F1D stroke. An irregular five-sided field polygon. Inside it, three short horizontal bars of different lengths, like a tiny score. No brain, no nodes, no chart axes, no text.
```

---

## 14. Threat / pest icon set

Sheet first, then singles if one fails. Olive stroke on paper. These are field-manual symbols. No horror, no swarm, no “infected crop” scene.

```
One horizontal row of 4 icons, equal size, equal gaps, paper #F4EDE6, olive #404F1D stroke only, no text, no labels, no color coding. 1 rice blast: a single leaf with a small diamond lesion. 2 brown planthopper: simple side-view insect with folded wings and long legs, not cute. 3 rice black bug: smaller oval shield bug, top view, six legs. 4 bacterial leaf blight: a leaf with a pale streak from the tip. Same stroke. Large padding around the row.
```

Singles:

```
Icon only. Rice blast. One rice leaf, olive #404F1D stroke on paper #F4EDE6, with one small diamond-shaped lesion. No text.
```

```
Icon only. Brown planthopper. Side view, olive #404F1D stroke on paper #F4EDE6. Folded wings, long hind legs, simple field-manual insect. Not a cartoon. No text.
```

```
Icon only. Rice black bug. Top view shield-shaped insect, olive #404F1D stroke on paper #F4EDE6. Compact, six legs. No text.
```

```
Icon only. Bacterial leaf blight. One long leaf, olive #404F1D stroke on paper #F4EDE6, with a wavy pale streak running from the tip. No text.
```

---

## 15. Risk level icon set

Same shape for every class so color and fill do the work. Square swatches match the map legend. Shape backup: 1 to 4 bars, for when color is not enough.

```
One horizontal row of 4 equal squares on paper #F4EDE6, no text. Each square is a flat swatch with 1 to 4 short cream bars inside. 1 Low, fill #7C914D, one bar. 2 Moderate, fill #A67C1F, two bars. 3 High, fill #D05327, three bars. 4 Very high, fill #DB2E27, four bars. Square corners. Equal gaps.
```

Singles:

```
Risk icon. Square swatch filled #7C914D, one short cream bar centered. Paper #F4EDE6 around it. Label nowhere. Low risk.
```

```
Risk icon. Square swatch filled #A67C1F, two short cream bars. Paper #F4EDE6 around it. Moderate risk. No text.
```

```
Risk icon. Square swatch filled #D05327, three short cream bars. Paper #F4EDE6 around it. High risk. No text.
```

```
Risk icon. Square swatch filled #DB2E27, four short cream bars. Paper #F4EDE6 around it. Very high risk. No text.
```

No-data companion, not part of the four-step scale:

```
Risk icon. Square swatch filled #B7B1A6, a single cream dot in the center. Paper #F4EDE6 around it. Means no data. No text.
```

---

## 16. Trend icon set

Arrows match the product change colors. Stable is stone, not green and not red.

```
One row of 3 icons, paper #F4EDE6, same stroke weight, no text. Rising: arrow up and to the right, color #9F2D2D. Stable: horizontal line with a short vertical tick at each end, color #B7B1A6. Falling: arrow down and to the right, color #2D6A4F. No chart, no grid.
```

Singles:

```
Icon only. Rising trend. Simple arrow pointing up-right, stroke #9F2D2D, on paper #F4EDE6. No text.
```

```
Icon only. Stable trend. Horizontal line with end ticks, stroke #B7B1A6, on paper #F4EDE6. No text.
```

```
Icon only. Falling trend. Simple arrow pointing down-right, stroke #2D6A4F, on paper #F4EDE6. No text.
```

---

## 17. Weather icon set

Layers in the product: temperature, rainfall, humidity, wind, soil moisture, leaf wetness. Seasons: wet and dry. Stroke olive unless the prompt names a data color.

```
One row of 6 weather icons, olive #404F1D stroke on paper #F4EDE6, no text, same size. 1 temperature: small sun circle with short rays. 2 rainfall: one cloud, three short vertical drops. 3 humidity: one drop beside three horizontal air lines. 4 wind: three horizontal lines, middle line longer. 5 soil moisture: a soil band with a drop above it. 6 leaf wetness: one leaf with a single drop. No rainbow, no storm drama.
```

Singles:

```
Icon. Temperature. Small circle and eight short rays, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Rainfall. Simple cloud and three drops, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Humidity. One drop and three short horizontal lines, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Wind. Three curved horizontal strokes, olive #404F1D, paper #F4EDE6. No text.
```

```
Icon. Soil moisture. Rectangle of soil with a drop above, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Leaf wetness. One leaf and one drop, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Wet season. Cloud over three short rice stems, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Dry season. Sun circle over three short rice stems, olive #404F1D stroke, paper #F4EDE6. No text.
```

---

## 18. Field / municipality icon set

Abstract polygons. Do not draw a real map of Nueva Ecija that could be read as an official boundary.

```
One row of 6 icons, olive #404F1D stroke on paper #F4EDE6, no text. 1 municipality: one irregular polygon. 2 barangay: a smaller polygon inside a larger one. 3 canal: two parallel lines, slightly curved. 4 river: one meandering line. 5 road: a line with a short center dash. 6 rice field: a rectangle split into three paddies. Same stroke.
```

Singles:

```
Icon. Municipality. One irregular five-sided polygon, olive #404F1D stroke, paper #F4EDE6. No text, no pin.
```

```
Icon. Barangay. Large polygon outline with a smaller polygon inside, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Canal. Two parallel gently curved lines, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. River. One meandering stroke, olive #404F1D, paper #F4EDE6. No text.
```

```
Icon. Road. Straight stroke with a dashed center, olive #404F1D, paper #F4EDE6. No text.
```

```
Icon. Rice field. Rectangle divided into three long paddies, olive #404F1D stroke, paper #F4EDE6. No text.
```

---

## 19. Inspection icon set

Inspection means a list of places to visit. Not a police badge. Not a clipboard cartoon character.

```
One row of 5 icons, olive #404F1D stroke on paper #F4EDE6, no text. 1 list: three lines with small square bullets. 2 add stop: a square field plus a small plus. 3 field note: a small rectangle page with one folded corner and two lines. 4 route: three dots joined by a path. 5 window: a small calendar square with a dot. Same stroke.
```

Singles:

```
Icon. Inspection list. Three horizontal lines, each with a small square at the left, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Add to inspection list. Square field outline and a plus sign, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Field note. Page with a folded corner and two text lines, olive #404F1D stroke, paper #F4EDE6. No letters that form words.
```

```
Icon. Inspection route. Three small circles connected by a thin path, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Visit window. Calendar square with one filled dot, olive #404F1D stroke, paper #F4EDE6. No text.
```

---

## 20. Satellite / remote sensing icon

The product uses satellite layers (NDVI, EVI, NDWI, LSWI, flood fraction, land surface temperature). The icon is a pass over a field, not a sci-fi satellite with solar panels as the brand.

```
Icon. Satellite sensing. A simple side-view satellite, two short panels, olive #404F1D stroke, above a rectangle split into paddies. Paper #F4EDE6. No text, no glow, no orbit rings.
```

```
Icon. Canopy index. A square of four flat cells in #C4A574, #A3B18A, #2D6A4F, and #1B4332. Paper #F4EDE6 around the square. No text, no legend.
```

---

## 21. Data / analytics icon set

```
One row of 5 icons, olive #404F1D stroke on paper #F4EDE6, no text. 1 hazard: a square containing the number-free mark of three rising bars. 2 priority: a horizontal bar three-quarters filled. 3 confidence: a circle broken into three arcs. 4 matrix: a 3 by 3 grid of small squares. 5 recompute: a circular arrow. Same stroke. No pie chart, no 3D bars.
```

Singles:

```
Icon. Hazard score. Three vertical bars of increasing height inside a square, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Priority. One horizontal track with a fill to about seventy percent, olive #404F1D, paper #F4EDE6. No text.
```

```
Icon. Confidence. Circle made of three separate arcs, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Municipality by threat matrix. Three by three small squares, olive #404F1D stroke, paper #F4EDE6. No text.
```

```
Icon. Recompute. One circular arrow, olive #404F1D stroke, paper #F4EDE6. No text.
```

---

## 22. Forecast icon

Seven-day forecast. The control in the product is Now, +1d … +6d.

```
Icon. Forecast. Seven short vertical ticks in a row, the first tick taller, olive #404F1D stroke on paper #F4EDE6. No numbers, no sun, no text.
```

---

## 23. Alert / warning icon set

Language is attention and change. Not emergency cosplay.

```
One row of 4 icons, no text, paper #F4EDE6. 1 new high: a small flag on a vertical stroke, color #D4652F. 2 watch: a diamond outline, olive #404F1D, empty inside. 3 rising alert: a triangle outline with an up arrow inside, color #9F2D2D. 4 missing data: a square outline, stroke #B7B1A6, with a short centered dash. No exclamation mark, no skull, no flame.
```

Singles:

```
Icon. New high. Small flag on a pole, stroke #D4652F, paper #F4EDE6. No text.
```

```
Icon. Watch. Empty diamond outline, olive #404F1D, paper #F4EDE6. Means look, not danger. No text.
```

```
Icon. Rising alert. Triangle outline in #9F2D2D with a small up arrow inside. Paper #F4EDE6. No exclamation mark, no text.
```

```
Icon. Missing data. Square outline #B7B1A6 with a short dash inside. Paper #F4EDE6. No text.
```

---

## 24. Map marker system

One family. The pin is a short stem under a square, not a teardrop map pin. Selected state is filled olive. Risk states use the risk fills. Clusters are pills, because the UI controls are pills.

```
Map marker sheet on paper #F4EDE6, one row, no text except a cluster may show the numeral 3 in olive. 1 default: small square #404F1D on a 4 px stem. 2 selected: larger filled square #404F1D on a stem. 3 low: square #7C914D. 4 moderate: square #A67C1F. 5 high: square #D05327. 6 very high: square #DB2E27. 7 no data: square #B7B1A6. 8 cluster: horizontal pill outline #404F1D containing the numeral 3. Same stem style. No teardrop pins, no shadows.
```

Singles if the sheet fails:

```
Map marker. Square olive #404F1D on a short vertical stem, centered, paper #F4EDE6. No text, no teardrop.
```

```
Selected map marker. Larger filled square #404F1D on a short stem, paper #F4EDE6. No text.
```

```
Cluster marker. Pill outline in olive #404F1D, the numeral 3 inside in olive, paper #F4EDE6. No shadow.
```

---

## 25. Map legend symbols

A legend strip, not a poster. Labels are allowed here because a legend without names is incomplete. Set the type in Helvetica, olive, small.

```
Map legend on paper #F4EDE6, left aligned, Helvetica, olive #404F1D type, no title. Five rows with square swatches: Low #7C914D, Moderate #A67C1F, High #D05327, Very high #DB2E27, No data #B7B1A6. Then four line samples: Canal, two parallel olive lines. River, one wavy olive line. Road, dashed olive line. Then four change rows: Increased #9F2D2D, Decreased #2D6A4F, New high #D4652F, Unchanged #D6D0C4, each a short horizontal bar. Quiet, like a field manual. No decorative frame.
```

---

## 26. Crop field pattern / texture

Seamless tile for empty states and print.

```
Seamless square pattern of aerial rice paddies. Flat shapes, no perspective photo. Paper #F4EDE6 ground, paddy lines in #E6D9C8, a few paddies filled sage #7C914D at low opacity. Irregular rectangles, Central Luzon irrigation grid. No houses, no text, no people. Tileable edges.
```

---

## 27. Brand background pattern

Two fields. Use the paper one behind light layouts and the black one behind the dark half of the brand.

```
Seamless brand pattern, paper #F4EDE6, with a very faint irrigation grid in #E6D9C8. Lines thin. A rare small tiller motif in sage #7C914D, sparse, not a wallpaper of logos. No text. Tileable.
```

```
Seamless brand pattern, solid black #000000, hairline paddy grid in #2C3816. Quiet. No text, no green glow. Tileable.
```

---

## 28. Brand geometric motif

The tiller reduced until it can repeat as a corner mark or a section break.

```
A single geometric motif centered on paper #F4EDE6: one vertical stem and two pairs of arcs for leaves, olive #404F1D, no ground line, no fill. Minimal enough to repeat in a corner. No text.
```

```
A horizontal rule for section breaks on paper #F4EDE6: a thin olive #404F1D line, interrupted at center by a tiny tiller stem and two leaves. Wide, short, no text.
```

---

## 29. Agricultural illustration style

Use this paragraph inside every illustration prompt.

```
Illustration style: flat editorial print. Limited colors only: paper #F4EDE6, black #000000, olive #404F1D, sage #7C914D, cream #F3EFE4, and at most one risk color. Shapes of flat color, or fine olive line. No outline sticker look, no anime, no 3D, no sunset gradient, no stock smile, no tablet glow, no food photography. Nueva Ecija: flat irrigated rice, canals, a low distant ridge, overcast morning light. People, if any, are small, seen working, not posing.
```

---

## 30. Rice field illustration

```
Wide illustration, 16:9. Irrigated rice paddies in Nueva Ecija under an overcast morning. Flat editorial print style. Paper #F4EDE6 sky, sage #7C914D and olive #404F1D paddies, canal as a pale line #E6D9C8, low gray-green ridge on the horizon. Water in the near paddy. No people, no text, no drone, no sunset.
```

---

## 31. Field inspection illustration

```
Illustration, 4:5. Two agriculture officers at the edge of a rice paddy, mid-distance, seen from the side, one holding a notebook. Clothing in olive #404F1D and stone #B7B1A6. Paddies in sage and paper. Overcast. Flat editorial print. They are observing, not celebrating. No logos on shirts, no readable text, no drone, no tablet screen.
```

---

## 32. Satellite / drone illustration

Drone stays in this one scene. It is not a logo.

```
Illustration, 16:9, split. Left: a simple satellite above a flat patchwork of paddies, fine olive line on paper. Right: a small quadcopter drone above one paddy, same line weight, no motion blur, no HUD, no neon. Colors: paper #F4EDE6, olive #404F1D, sage #7C914D, water blue-gray #8FB4C9 used once. No text, no lens flare.
```

---

## 33. Weather / forecast illustration

```
Illustration, 16:9. A quiet seven-day strip above a rice horizon. Seven equal columns. Sky shifts from dry paper light to a wet gray-blue #8FB4C9 and back, using flat shapes. Below, the same paddy line in olive. No numbers, no city, no storm destruction. Paper, olive, sage, one blue-gray. Editorial, not a weather-app mascot.
```

---

## 34. CROPWATCH AI assistant avatar / icon

The assistant is “Ask CROPWATCH.” The avatar is the tiller in a circle. No face, no sparkle, no robot.

```
Avatar icon, circle filled paper #F4EDE6 with a thin olive #404F1D ring. Inside, the CROPWATCH tiller, olive stroke, centered. No face, no eyes, no antenna, no speech bubble, no text.
```

```
Avatar icon for dark UI. Circle filled black #000000. Inside, the tiller in cream #F3EFE4, stroke only. No face, no text.
```

---

## 35. Loading animation concept

Gemini should draw a storyboard, not a video. Motion in the product is 700 ms, ease out. Reduced motion is the finished mark, still.

```
Storyboard of 4 frames in a row on paper #F4EDE6, equal squares, no text, no play button. Olive #404F1D stroke. Frame 1: only the vertical stem. Frame 2: stem plus two upper leaves. Frame 3: stem plus four leaves. Frame 4: complete tiller with the ground line. Same position every frame so it can be read as a draw-on animation. Thin frame numbers are not wanted.
```

---

## 36. Risk transition animation concept

A polygon fill changes class. It does not flash.

```
Storyboard of 4 frames, same municipality polygon, centered, paper #F4EDE6, no text. Frame 1 fill low #7C914D. Frame 2 fill moderate #A67C1F. Frame 3 fill high #D05327. Frame 4 fill very high #DB2E27. Outline stays olive #404F1D. Identical shape and position. No glow, no shake, no warning stripes.
```

---

## 37. Map / location animation concept

```
Storyboard of 4 frames, paper #F4EDE6, no text. Frame 1: blank. Frame 2: olive polygon outline half drawn. Frame 3: polygon closed, still empty. Frame 4: polygon with a small olive square marker on a stem inside it. Same crop every frame. No bouncing pin, no radar rings.
```

---

## 38. Data visualization motif

The product’s charts are bars, heat cells, and hairline tables. This motif is the pattern to reuse.

```
Data visualization specimen on paper #F4EDE6. Left: five horizontal bars in olive #404F1D, different lengths, no axes, no numbers. Center: a 4 by 5 grid of square cells using only #7C914D, #A67C1F, #D05327, #DB2E27, and #B7B1A6. Right: three hairline rows in #E6D9C8 with short olive labels that are not real words, just lines. Flat, print-like, no 3D, no donut chart, no title.
```

---

## 39. Brand photography direction

Grade every photograph toward paper highlights and olive shadows. Overcast or early morning. Central Luzon rice. Documentary distance. No teal-and-orange grade, no golden-hour hero, no rice-bowl food shot, no drone light painting.

Shoot list:

```
Documentary photograph, overcast morning, aerial oblique of irrigated rice paddies in Nueva Ecija, Philippines. Water, bunds, one canal. Color grade muted: highlights near #F4EDE6, vegetation near olive and sage, no saturated lime, no sunset. No text, no people.
```

```
Documentary photograph, eye level at a paddy bund, young rice in standing water, soft overcast light, muted olive and paper tones. Shallow depth of field. No hands in frame, no text.
```

```
Documentary photograph, two Filipino agriculture workers at a distance walking a paddy edge with a notebook, overcast, unposed, muted grade toward #F4EDE6 and #404F1D. Faces not featured. No logos, no smile-to-camera, no drone.
```

```
Still life, top view: paper map print, a pencil, a small soil-stained notebook, on a wood table, muted paper and olive grade. No brand names, no laptop, no phone screen.
```

```
Detail photograph of a rice leaf with a single natural lesion, soft light, scientific and calm, muted color. Not gore, not a macro horror shot. No text, no arrows.
```

Avoid in photography: children, distress, dead livestock, pesticide spraying close-ups, military framing, fake HUD overlays, stock handshakes, hard hats as costume.

---

## 40. Full brand identity board

One board. Ask for it after the logo lockup looks right, and attach that lockup if the tool allows a reference image.

```
A brand identity board, 16:9, paper #F4EDE6 background, generous margins, quiet editorial layout, not a crowded startup poster.

Top left: horizontal CROPWATCH lockup, tiller plus the word CROPWATCH, olive #404F1D, Helvetica Neue Medium, all caps.
Top right: the same lockup in cream #F3EFE4 on a black #000000 rectangle.
Under that: the tiller symbol large, stroke only, olive.

A row of color chips with no hex labels: #F4EDE6, #000000, #404F1D, #2C3816, #7C914D, #E6D9C8, #F3EFE4. Then a second row of risk chips: #7C914D, #A67C1F, #D05327, #DB2E27, #B7B1A6.

A row of 8 small olive icons: rice tiller, field polygon, rain, inspection list, satellite, rising arrow, forecast ticks, square map marker.

Bottom band, full width: a flat illustration of Nueva Ecija paddies and one canal, overcast, sage and olive on paper, no people, no extra words.

The only rendered word is CROPWATCH. No lorem ipsum, no fake slogans, no mock browser, no phone, no 3D, no gradient mesh.
```

Dark companion board:

```
Brand board on black #000000, 16:9. Cream #F3EFE4 tiller and the word CROPWATCH. A thin paper #F4EDE6 panel containing the olive lockup. Risk chips in a single row. Sparse cream icons. Lots of empty black. The only word is CROPWATCH.
```

---

## Regeneration notes

- If the tiller grows grains, a sun, or a second plant, rerun with: “exactly one stem, exactly four leaves, one ground line.”
- If the green turns neon, rerun with: “olive ink #404F1D, sap green, not lime, not emerald.”
- If letters appear inside an icon, rerun with: “no letters, no numerals, no watermark.”
- If the lockup uses a serif or a custom logotype, rerun with: “Helvetica Neue Medium, ordinary letterforms, tight tracking.”
- If insects look like mascots, rerun with: “entomology plate, unsmiling, stroke only, no eyes emphasized.”
- If risk icons change shape between classes, rerun with: “identical squares, only the fill color and the number of bars change.”
- Keep risk reds off the wordmark. A red CROPWATCH reads as an alarm, and the product is a monitoring tool.
