require "rails_helper"

describe "Leaderboard" do
  it "shows worts in descending order of their weighted score for this season" do
    last_wort = create(:user)
    first_wort = create(:user)
    middle_wort = create(:user)

    create_list(:trophy, 3, :category_2nd, user: middle_wort)    # 6 points
    create(:trophy, :category_1st, user: last_wort)              # 3 points
    create_list(:trophy, 2, :best_of_show_2nd, user: first_wort) # 8 points

    visit "/"
    click_link "Leaderboard"

    expect(page).to have_leaderboard_row(
      first_wort,
      row_number: 1,
      score: 8,
    )
    expect(page).to have_leaderboard_row(
      middle_wort,
      row_number: 2,
      score: 6,
    )
    expect(page).to have_leaderboard_row(
      last_wort,
      row_number: 3,
      score: 3,
    )
  end

  def have_leaderboard_row(user, row_number:, score:)
    row = "tr[id='user-#{user.id}']:nth-child(#{row_number})"
    have_css(row, text: score)
  end
end
