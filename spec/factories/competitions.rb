FactoryBot.define do
  factory :competition do
    competition_type CompetitionType::TYPES.first
    date { Date.today }
    name "MyString"
    url "MyString"
  end
end
