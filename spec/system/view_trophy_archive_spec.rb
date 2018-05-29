require "rails_helper"

describe "Trophy archive" do
  it "lets you see trophies from past years" do
    this_season_trophy = create(:trophy)
    last_season_date = 1.year.ago
    last_season_competition = create(:competition, date: last_season_date)
    last_season_trophy = create(:trophy, competition: last_season_competition)

    visit "/trophies"

    expect(page).to have_selected_season(this_season_trophy.season)
    expect(page).to have_trophy_row(this_season_trophy)
    expect(page).not_to have_trophy_row(last_season_trophy)

    click_link last_season_trophy.season.description

    expect(page).to have_selected_season(last_season_trophy.season)
    expect(page).to have_trophy_row(last_season_trophy)
    expect(page).not_to have_trophy_row(this_season_trophy)
  end

  def have_trophy_row(trophy)
    have_css("tr[id='trophy-#{trophy.id}']")
  end

  def have_selected_season(season)
    have_css(".tabnav-tab.selected", text: season.description)
  end
end
