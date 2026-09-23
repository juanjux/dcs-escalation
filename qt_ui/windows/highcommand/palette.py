"""The High Command's colours: the window's palette plus one hue of its own.

The orange marks the High Command wherever it appears: the window, the command bar
cell and the line in a point's window. It is warmer and more saturated than the cheat
amber (#E0A86B), so the two are not confused.
"""

#: The High Command orange: the window's band, tickets, the last turn, Spend.
ORANGE = "#F29A4A"
#: Text on a solid orange chip.
ON_ORANGE = "#0F1922"
#: The fill of a TICKET or SPENT chip.
TICKET_FILL = "#3D2A1B"
#: The fill of an order in its last turn, and of the line in a point's window.
LAST_TURN_FILL = "#231E1A"
#: The border of the line in a point's window.
POINT_LINE_BORDER = "#4A3322"
#: The fill of an INSTANT chip, and its text.
INSTANT_FILL = "#23372D"
INSTANT = "#86C39A"

WINDOW = "#2D3E50"
HEADER = "#1B2732"
CARD = "#14202B"
CARD_BORDER = "#1D2731"
DIVIDER = "#1D2731"
HOVER = "#1A2A38"
SELECTED = "#1E3A52"
SELECTED_BAR = "#8FC3F0"

TITLE = "#F2F7FA"
BODY = "#D3DFE8"
SOFT = "#B7C6D2"
QUIET = "#8E9DAA"
MUTED = "#7C8B99"
CAPTION = "#6B7A87"
PIP_OFF = "#26343F"

#: The tier chips, as (fill, text).
TIERS = {
    "high": ("#2B4A66", "#BEDCF6"),
    "medium": ("#26343F", "#B7C6D2"),
    "low": ("#1D2731", "#8E9DAA"),
}
