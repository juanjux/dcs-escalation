# Selected fighter icon: contrast refinement

The user selected proposal 04. This revision adds a navy outline so the ivory silhouette remains readable on light backgrounds. Generated through the built-in image tool in edit mode. Runtime assets are unchanged pending refinement approval.

![Outlined fighter](04-simple-jet-outlined.png)

## Outline edit prompt

Use case: precise-object-edit. Edit the supplied selected DCS Escalation app icon, not a redesign. Preserve exactly the F-16-style single fighter silhouette angled upper right and the two blue and yellow short parallel trail bars, their positions, size and proportions. Keep ivory aircraft fill. Add a clean continuous dark navy #142640 outline around the aircraft AND both trail bars, thick enough to survive reduction to a 32-pixel Windows icon (approximately 25 pixels thick at this full resolution), with smooth precise edges. This outline is the only design change, ensuring readability on pure white backgrounds while the ivory fill ensures readability on dark backgrounds. Remove rough edge speckles. Absolutely flat fills, no shadows, no glows, no gradients, no 3D, no extra internal aircraft detail, no enclosing badge or square tile, no text. Genuine transparent alpha background outside the outlined shapes. Single icon, no comparison sheet. Preserve composition and generous margins.

## Alpha correction prompt

The first edit painted a checkerboard into an RGB image. A second built-in edit removed it:

Use case: background-extraction. The supplied image is the edit target. Remove the ENTIRE gray checkerboard background and ALL background residue, and output an actual transparent PNG with an alpha channel, NOT a painted checkerboard, NOT a white or black background. Keep only the single ivory fighter silhouette with its dark navy border and its blue and yellow parallel bars. Preserve the icon's shape, colors, position and proportions exactly. Smooth clean antialiased edges. No new elements, no text, no shadows. Transparent pixels everywhere outside the navy outline. This is an isolated Windows application icon asset.
