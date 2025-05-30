int GetTextBounds(esphome::display::Display* it, esphome::font::Font *font, const char *buffer)
{
    int x1 = 0;     // A pointer to store the returned x coordinate of the upper left corner in. 
    int y1 = 0;     // A pointer to store the returned y coordinate of the upper left corner in.
    int width = 0;  // A pointer to store the returned text width in.
    int height = 0; // A pointer to store the returned text height in. 
    it->get_text_bounds(0, 0, buffer, font, TextAlign::TOP_LEFT, &x1, &y1, &width, &height);
    return width;
}

int GetTextWidth(esphome::display::Display* it, esphome::font::Font *font, const char* formatting, const char *raw_text){
    char temp_buffer[80];
    sprintf(temp_buffer, formatting, raw_text);
    return GetTextBounds(it, font, temp_buffer);
}

int GetTextWidth(esphome::display::Display* it, esphome::font::Font *font, const char* formatting){
    char temp_buffer[80];
    sprintf(temp_buffer, formatting);
    return GetTextBounds(it, font, temp_buffer);
}

int GetTextWidth(esphome::display::Display* it, esphome::font::Font *font, const char* formatting, float& raw_text){
    char temp_buffer[80];
    sprintf(temp_buffer, formatting, raw_text);
    return GetTextBounds(it, font, temp_buffer);
}

int GetTextWidth(esphome::display::Display* it, esphome::font::Font *font, const char* formatting, float& raw_text1, float& raw_text2){
    char temp_buffer[80];
    sprintf(temp_buffer, formatting, raw_text1, raw_text2);
    return GetTextBounds(it, font, temp_buffer);
}

// Calculate the width of time format
int GetTextWidth(esphome::display::Display* it, esphome::font::Font *font, const char* formatting, esphome::ESPTime time){
    auto c_tm = time.to_c_tm();
    size_t buffer_length = 80;
    char temp_buffer[buffer_length];
    strftime(temp_buffer, buffer_length, formatting, &c_tm);
    return GetTextBounds(it, font, temp_buffer);
}

std::string extract_time(const char* datetime) {
    // Assume datetime is in the format "YYYY-MM-DDTHH:MM:SS+XX:XX"
    std::string datetimeStr(datetime);
    size_t pos = datetimeStr.find('T'); // Find the position of 'T' which separates date and time
    if (pos != std::string::npos && pos + 3 < datetimeStr.size()) {
        // Extract the time part after 'T'
        std::string timeStr = datetimeStr.substr(pos + 1, 5); // Assuming time format is "HH:MM"
        return timeStr;
    }
    return "";
}

// Code based on https://community.home-assistant.io/t/centering-text-when-using-multiple-printf/491205/14

std::array<int, 2> get_text_bounds(esphome::display::Display* display, esphome::font::Font* font, const char* text) {
    int x1 = 0, y1 = 0, width = 0, height = 0;
    display->get_text_bounds(0, 0, text, font, TextAlign::BOTTOM_CENTER, &x1, &y1, &width, &height);
    return {width, height};
}

// Function template for formatting text and getting its dimension
template<typename T>
int get_text_dimension(esphome::display::Display* display, esphome::font::Font* font, const char* formatting, const T& value, bool getWidth) {
    char buffer[80];
    std::sprintf(buffer, formatting, value);
    auto bounds = get_text_bounds(display, font, buffer);
    return getWidth ? bounds[0] : bounds[1];
}

// Specialization for esphome::ESPTime
int get_text_dimension(esphome::display::Display* display, esphome::font::Font* font, const char* formatting, esphome::ESPTime& time, bool getWidth) {
    std::tm c_tm = time.to_c_tm();
    char buffer[80];
    std::strftime(buffer, sizeof(buffer), formatting, &c_tm);
    auto bounds = get_text_bounds(display, font, buffer);
    return getWidth ? bounds[0] : bounds[1];
}

// Utility functions to get width or height
template<typename T>
int get_text_width(esphome::display::Display* display, esphome::font::Font* font, const char* formatting, const T& value) {
    return get_text_dimension(display, font, formatting, value, true);
}

template<typename T>
int get_text_height(esphome::display::Display* display, esphome::font::Font* font, const char* formatting, const T& value) {
    return get_text_dimension(display, font, formatting, value, false);
}

// End code based on https://community.home-assistant.io/t/centering-text-when-using-multiple-printf/491205/14