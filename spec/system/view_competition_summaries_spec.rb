require "rails_helper"

describe "Competition summary" do
  it "shows medal breakdowns for each competition" do
    comp = create(:competition)
    create_pair(:trophy, :category_1st, competition: comp)
    create_list(:trophy, 3, :category_2nd, competition: comp)
    create(:trophy, :best_of_show_1st, competition: comp)
    create(:trophy, :best_of_show_2nd, competition: comp)

    visit "/competitions"

    expect(page).to have_content "Category Awards: 🥇🥇🥈🥈🥈"
    expect(page).to have_content "Best Of Show Awards: 🏆🏆"

    click_link "🥇🥇🥈🥈🥈"

    expect(page).to have_current_path trophies_by_season_path(comp.season, competition_id: comp)
    expect(page).to have_css("option[selected='selected']", text: comp.name)
  end
end
