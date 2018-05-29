require "rails_helper"

describe "Trophy archive" do
  it "lets you see trophies from past years" do
    this_year_trophy = create(:trophy)
    last_year_date = 1.year.ago
    last_year_competition = create(:competition, date: last_year_date)
    last_year_trophy = create(:trophy, competition: last_year_competition)

    visit "/"

    expect(page).to have_selected_year(Date.today.year)
    expect(page).to have_trophy_row(this_year_trophy)
    expect(page).not_to have_trophy_row(last_year_trophy)

    click_link last_year_date.year

    expect(page).to have_selected_year(last_year_date.year)
    expect(page).to have_trophy_row(last_year_trophy)
    expect(page).not_to have_trophy_row(this_year_trophy)
  end

  def have_trophy_row(trophy)
    have_css("tr[id='trophy-#{trophy.id}']")
  end

  def have_selected_year(year)
    have_css(".tabnav-tab.selected", text: year)
  end
end
