// Client-side location heuristics for the "US only" / "Remote only" toggles.
// The backend /jobs endpoint has no country or work-type filter, so these
// run against the already-fetched page in the browser.

const NON_US_LOCATION_RE =
    /\b(canada|india|united kingdom|uk|england|scotland|wales|ireland|germany|france|spain|italy|netherlands|sweden|poland|portugal|australia|new zealand|singapore|japan|china|brazil|mexico|argentina|colombia|europe|emea|apac|latam|asia|bengaluru|gurugram|hyderabad|mumbai|pune|budapest|london|dublin|cork|remote poland|remote spain|remote\s*[-,]?\s*in\b|hybrid - madrid)\b/i;
const NON_US_COUNTRY_CODE_RE =
    /(^|[\s,(/-])(IE|GB|UK|IN|DE|FR|ES|PL|NL|BR|MX|AU|NZ|SG|JP|CN)(?=$|[\s,)/-])/;
const US_LOCATION_RE =
    /\b(united states|usa|u\.s\.a\.|u\.s\.|us only|remote us|remote - us|remote \(us\)|america|north america|alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming|washington dc|district of columbia|nyc|indianapolis|fort wayne|evansville|south bend|carmel|fishers|bloomington|san francisco|los angeles|seattle|austin|boston|chicago|atlanta|denver|miami|dallas|houston|phoenix|portland|philadelphia|nashville|raleigh|charlotte|san diego|san jose|bellevue|redmond|mountain view|menlo park|palo alto|santa clara|sunnyvale|cupertino|san mateo|fremont|el segundo|irvine|tampa|reston|herndon)\b/i;
const US_STATE_CODE_RE =
    /(^|[\s,(/-])(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?=$|[\s,)/-])/;

export function isUsLocation(location: string): boolean {
    const normalized = (location || "").replace(/\s+/g, " ").trim();
    if (!normalized) return false;
    if (/^remote$/i.test(normalized)) return true;
    if (/\b(indianapolis|fort wayne|evansville|south bend|carmel|fishers|bloomington)\b/i.test(normalized)) return true;
    if (NON_US_LOCATION_RE.test(normalized) || NON_US_COUNTRY_CODE_RE.test(normalized)) return false;
    return US_LOCATION_RE.test(normalized) || US_STATE_CODE_RE.test(normalized);
}

export function isRemoteLocation(location: string): boolean {
    return /remote/i.test(location || "");
}
