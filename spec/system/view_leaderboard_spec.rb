require "rails_helper"

describe "Leaderboard" do
  it "shows worts in descending order of their weighted score for this season" do
    last_wort = create(:user)
    first_wort = create(:user)
    middle_wort = create(:user)

    create_list(:trophy, 3, :category_2nd, user: middle_wort)    # 6 points
    create(:trophy, :category_1st, user: last_wort)              # 3 points
    create_list(:trophy, 2, :best_of_show_2nd, user: first_wort) # 12 points

    visit "/leaderboard"

    [first_wort, middle_wort, last_wort].each.with_index(1) do |wort, row_num|
      expect(page).to have_leaderboard_row(wort, row_number: row_num)
    end
  end

  def have_leaderboard_row(user, row_number:)
    have_css("tr[id='user-#{user.id}']:nth-child(#{row_number})")
  end
end
