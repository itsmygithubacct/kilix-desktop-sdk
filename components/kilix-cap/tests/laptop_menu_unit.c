#include <assert.h>
#include "../src/scene.c"
void sound_play(SoundCue cue) { (void)cue; }
static void click_slot(int slot)
{
    UiRect card = laptop_menu_card();
    input_event event = {0};
    event.in_view = true;
    event.mx = card.x + card.w / 2;
    event.my = card.y + laptop_menu_header_height() + slot * LAPTOP_MENU_ROW_H + 36;
    event.kind = IN_MOUSE_DOWN; assert(laptop_menu_handle(&event));
    event.kind = IN_MOUSE_UP; assert(laptop_menu_handle(&event));
}
int main(void)
{
    for (int count = 0; count <= LAPTOP_PROFILES_MAX; count++) {
        LaptopList list = {0}; list.count = count;
        for (int i = 0; i < count; i++) snprintf(list.ids[i], LAPTOP_ID_MAX, "profile-%d", i);
        scene_set_laptop_profiles(&list);
        int pages = count ? (count + LAPTOP_MENU_PAGE_SIZE - 1) / LAPTOP_MENU_PAGE_SIZE : 1;
        for (int page = 0; page < pages; page++) {
            assert(laptop_menu.page == page);
            UiRect card = laptop_menu_card();
            assert(card.y >= CONTENT_Y && card.y + card.h <= CONTENT_Y + CONTENT_H);
            int visible = laptop_menu_visible_profiles();
            for (int slot = 0; slot < visible; slot++) {
                int row = page * LAPTOP_MENU_PAGE_SIZE + slot;
                for (int running = 0; running <= 1; running++) {
                    laptop_menu.open = true;
                    laptop_menu_running[row] = running;
                    click_slot(slot);
                    const char *id = NULL;
                    assert(running ? scene_take_laptop_close_request(&id) : scene_take_laptop_request(&id));
                    assert(strcmp(id, list.ids[row]) == 0 && !laptop_menu.open);
                }
            }
            laptop_menu.open = true;
            click_slot(laptop_menu_rows() - 1);
            assert(!laptop_menu.open);
            if (pages > 1) {
                laptop_menu.open = true; click_slot(visible);
                assert(laptop_menu.open && laptop_menu.page == (page + 1) % pages);
            }
        }
    }
    puts("chooser reachability (0..16 profiles, open and close): passed");
}
